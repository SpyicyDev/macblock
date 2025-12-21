from __future__ import annotations

import hashlib
import re
import urllib.request
from pathlib import Path

from macblock.colors import info, success
from macblock.constants import (
    APP_LABEL,
    DEFAULT_BLOCKLIST_SOURCE,
    SYSTEM_BLACKLIST_FILE,
    SYSTEM_BLOCKLIST_FILE,
    SYSTEM_RAW_BLOCKLIST_FILE,
    SYSTEM_STATE_FILE,
    SYSTEM_WHITELIST_FILE,
    VAR_DB_DNSMASQ_PID,
    BLOCKLIST_SOURCES,
)
from macblock.launchd import kickstart, service_exists
from macblock.errors import MacblockError
from macblock.exec import run
from macblock.fs import atomic_write_text
from macblock.state import State, load_state, save_state_atomic


_domain_re = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*$", re.IGNORECASE)


def normalize_domain(domain: str) -> str:
    d = domain.strip().lower().strip(".")
    if not d:
        raise MacblockError("invalid domain")
    if not _domain_re.match(d):
        raise MacblockError("invalid domain")
    return d


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def _parse_hosts_domains(text: str) -> set[str]:
    domains: set[str] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0].strip()
        parts = line.split()
        if len(parts) < 2:
            continue

        for token in parts[1:]:
            try:
                d = normalize_domain(token)
            except MacblockError:
                continue
            if d in {"localhost", "localhost.localdomain"}:
                continue
            domains.add(d)

    return domains


def compile_blocklist(raw_path: Path, whitelist_path: Path, blacklist_path: Path, out_path: Path) -> int:
    raw = raw_path.read_text(encoding="utf-8") if raw_path.exists() else ""
    base = _parse_hosts_domains(raw)

    allow = {normalize_domain(x) for x in _read_lines(whitelist_path)}
    deny = {normalize_domain(x) for x in _read_lines(blacklist_path)}

    final = (base - allow) | deny

    lines = [f"address=/{d}/" for d in sorted(final)]
    atomic_write_text(out_path, "\n".join(lines) + ("\n" if lines else ""), mode=0o644)

    return len(final)


_MAX_BLOCKLIST_BYTES = 20 * 1024 * 1024


def _download(url: str, *, expected_sha256: str | None = None) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "macblock/0.0.0"},
    )

    hasher = hashlib.sha256()
    chunks: list[bytes] = []
    total = 0

    with urllib.request.urlopen(req, timeout=30) as resp:
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_BLOCKLIST_BYTES:
                raise MacblockError(f"blocklist too large (>{_MAX_BLOCKLIST_BYTES} bytes)")
            hasher.update(chunk)
            chunks.append(chunk)

    if expected_sha256 is not None:
        expected = expected_sha256.strip().lower()
        actual = hasher.hexdigest()
        if expected != actual:
            raise MacblockError(f"sha256 mismatch: expected {expected}, got {actual}")

    return b"".join(chunks).decode("utf-8", errors="replace")


def reload_dnsmasq() -> None:
    label = f"{APP_LABEL}.dnsmasq"
    if service_exists(label):
        kickstart(label)
        return

    if VAR_DB_DNSMASQ_PID.exists():
        try:
            pid = int(VAR_DB_DNSMASQ_PID.read_text(encoding="utf-8").strip())
        except Exception:
            pid = 0
        if pid > 1:
            run(["/bin/kill", "-HUP", str(pid)])


def update_blocklist(source: str | None = None, sha256: str | None = None) -> int:
    st = load_state(SYSTEM_STATE_FILE)
    chosen = source or st.blocklist_source or DEFAULT_BLOCKLIST_SOURCE

    if chosen.startswith("https://"):
        url = chosen
    elif chosen in BLOCKLIST_SOURCES:
        url = str(BLOCKLIST_SOURCES[chosen]["url"])
    else:
        raise MacblockError("unknown source")

    info("downloading")
    raw = _download(url, expected_sha256=sha256)

    atomic_write_text(SYSTEM_RAW_BLOCKLIST_FILE, raw, mode=0o644)

    count = compile_blocklist(SYSTEM_RAW_BLOCKLIST_FILE, SYSTEM_WHITELIST_FILE, SYSTEM_BLACKLIST_FILE, SYSTEM_BLOCKLIST_FILE)

    save_state_atomic(
        SYSTEM_STATE_FILE,
        State(schema_version=st.schema_version, enabled=st.enabled, resume_at_epoch=st.resume_at_epoch, blocklist_source=chosen),
    )

    reload_dnsmasq()

    success(f"blocklist entries: {count}")
    return 0
