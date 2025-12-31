from __future__ import annotations

import hashlib
import re
import sys
import urllib.request
from pathlib import Path

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
from macblock.state import load_state, replace_state, save_state_atomic
from macblock.ui import (
    dim,
    green,
    result_success,
    Spinner,
    step_done,
    SYMBOL_ACTIVE,
)


_domain_re = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*$",
    re.IGNORECASE,
)


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


def compile_blocklist(
    raw_path: Path, whitelist_path: Path, blacklist_path: Path, out_path: Path
) -> int:
    raw = raw_path.read_text(encoding="utf-8") if raw_path.exists() else ""
    base = _parse_hosts_domains(raw)

    allow: set[str] = set()
    if whitelist_path.exists():
        for i, line in enumerate(
            whitelist_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            try:
                allow.add(normalize_domain(s))
            except MacblockError:
                print(
                    f"warning: invalid domain in {whitelist_path.name}:{i}: {s}",
                    file=sys.stderr,
                )

    deny: set[str] = set()
    if blacklist_path.exists():
        for i, line in enumerate(
            blacklist_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            try:
                deny.add(normalize_domain(s))
            except MacblockError:
                print(
                    f"warning: invalid domain in {blacklist_path.name}:{i}: {s}",
                    file=sys.stderr,
                )

    final = (base - allow) | deny

    lines = [f"server=/{d}/" for d in sorted(final)]
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
        content_type = None
        if hasattr(resp, "headers"):
            content_type = resp.headers.get("Content-Type")

        if content_type and "text/html" in content_type.lower():
            raise MacblockError(
                f"downloaded blocklist looks like HTML (Content-Type: {content_type})"
            )

        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_BLOCKLIST_BYTES:
                raise MacblockError(
                    f"blocklist too large (>{_MAX_BLOCKLIST_BYTES} bytes)"
                )
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
        try:
            kickstart(label)
        except Exception as e:
            raise MacblockError(f"failed to reload dnsmasq via launchd: {e}") from e
        return

    if not VAR_DB_DNSMASQ_PID.exists():
        raise MacblockError("dnsmasq is not running (pid file missing)")

    try:
        pid = int(VAR_DB_DNSMASQ_PID.read_text(encoding="utf-8").strip())
    except Exception as e:
        raise MacblockError(f"dnsmasq pid file unreadable: {e}") from e

    if pid <= 1:
        raise MacblockError(f"dnsmasq is not running (invalid pid: {pid})")

    r = run(["/bin/kill", "-HUP", str(pid)])
    if r.returncode != 0:
        detail = (r.stderr or r.stdout).strip() or "unknown error"
        raise MacblockError(f"failed to reload dnsmasq (pid={pid}): {detail}")


def list_blocklist_sources() -> int:
    st = load_state(SYSTEM_STATE_FILE)
    current = st.blocklist_source or DEFAULT_BLOCKLIST_SOURCE

    print()
    for key in sorted(BLOCKLIST_SOURCES.keys()):
        if key == current:
            print(
                f"  {green(SYMBOL_ACTIVE)} {green(key)} - {BLOCKLIST_SOURCES[key]['name']}"
            )
        else:
            print(f"    {key} - {dim(str(BLOCKLIST_SOURCES[key]['name']))}")
    print()

    return 0


def set_blocklist_source(source: str) -> int:
    src = source.strip()

    if not src:
        raise MacblockError("source is required")

    if not (src.startswith("https://") or src in BLOCKLIST_SOURCES):
        raise MacblockError("unknown source")

    st = load_state(SYSTEM_STATE_FILE)
    save_state_atomic(
        SYSTEM_STATE_FILE,
        replace_state(st, blocklist_source=src),
    )

    step_done(f"Blocklist source set to {src}")
    print()
    return 0


def update_blocklist(source: str | None = None, sha256: str | None = None) -> int:
    st = load_state(SYSTEM_STATE_FILE)
    chosen = source or st.blocklist_source or DEFAULT_BLOCKLIST_SOURCE

    prev_state_text: str | None = None
    if SYSTEM_STATE_FILE.exists():
        prev_state_text = SYSTEM_STATE_FILE.read_text(
            encoding="utf-8", errors="replace"
        )

    prev_raw_text: str | None = None
    if SYSTEM_RAW_BLOCKLIST_FILE.exists():
        prev_raw_text = SYSTEM_RAW_BLOCKLIST_FILE.read_text(
            encoding="utf-8", errors="replace"
        )

    prev_blocklist_text: str | None = None
    if SYSTEM_BLOCKLIST_FILE.exists():
        prev_blocklist_text = SYSTEM_BLOCKLIST_FILE.read_text(
            encoding="utf-8", errors="replace"
        )

    did_write_blocklist = False
    did_write_state = False

    def _rollback() -> None:
        errors: list[str] = []

        def _restore(path: Path, previous: str | None) -> None:
            if previous is None:
                if path.exists():
                    path.unlink()
            else:
                atomic_write_text(path, previous, mode=0o644)

        try:
            if did_write_state:
                _restore(SYSTEM_STATE_FILE, prev_state_text)
        except Exception as e:
            errors.append(f"state.json: {e}")

        try:
            if did_write_blocklist:
                _restore(SYSTEM_RAW_BLOCKLIST_FILE, prev_raw_text)
                _restore(SYSTEM_BLOCKLIST_FILE, prev_blocklist_text)
        except Exception as e:
            errors.append(f"blocklist files: {e}")

        if errors:
            raise MacblockError("rollback failed: " + "; ".join(errors))

    if chosen.startswith("https://"):
        url = chosen
        source_name = "custom URL"
    elif chosen in BLOCKLIST_SOURCES:
        url = str(BLOCKLIST_SOURCES[chosen]["url"])
        source_name = chosen
    else:
        raise MacblockError("unknown source")

    print()

    # Download with spinner
    with Spinner(f"Downloading blocklist ({source_name})") as spinner:
        try:
            raw = _download(url, expected_sha256=sha256)
        except Exception as e:
            spinner.fail(f"Download failed: {e}")
            raise

        if not raw.strip():
            spinner.fail("Downloaded blocklist is empty")
            raise MacblockError("downloaded blocklist is empty")

        head = raw.lstrip()[:4096].lower()
        if (
            head.startswith("<!doctype html")
            or head.startswith("<html")
            or "<html" in head
        ):
            spinner.fail("Downloaded file looks like HTML, not a blocklist")
            raise MacblockError("downloaded blocklist looks like HTML")

        spinner.succeed("Downloaded blocklist")

    # Parse and compile
    count = 0
    with Spinner("Compiling blocklist") as spinner:
        count_raw = len(_parse_hosts_domains(raw))
        if count_raw < 1000:
            spinner.fail(f"Blocklist looks too small ({count_raw} domains)")
            raise MacblockError(
                "downloaded blocklist looks too small; refusing to apply (try a different source)"
            )

        atomic_write_text(SYSTEM_RAW_BLOCKLIST_FILE, raw, mode=0o644)
        did_write_blocklist = True
        try:
            count = compile_blocklist(
                SYSTEM_RAW_BLOCKLIST_FILE,
                SYSTEM_WHITELIST_FILE,
                SYSTEM_BLACKLIST_FILE,
                SYSTEM_BLOCKLIST_FILE,
            )
        except Exception as e:
            spinner.fail(f"Compile failed: {e}")
            _rollback()
            raise

        spinner.succeed(f"Compiled {count:,} domains")

    # Save state
    try:
        save_state_atomic(
            SYSTEM_STATE_FILE,
            replace_state(st, blocklist_source=chosen),
        )
        did_write_state = True
    except Exception as e:
        _rollback()
        raise MacblockError(f"failed to save state: {e}") from e

    # Reload dnsmasq
    with Spinner("Reloading dnsmasq") as spinner:
        try:
            reload_dnsmasq()
            spinner.succeed("Reloaded dnsmasq")
        except Exception as e:
            spinner.fail(f"Reload failed: {e}")
            try:
                _rollback()
            except Exception as rollback_err:
                raise MacblockError(
                    f"reload failed and rollback was incomplete: {rollback_err}"
                ) from e
            raise MacblockError(f"failed to reload dnsmasq: {e}") from e

    result_success(f"Blocklist updated: {count:,} domains blocked")
    print()
    return 0
