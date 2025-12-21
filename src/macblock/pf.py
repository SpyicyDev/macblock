from __future__ import annotations

import ipaddress
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager


import fcntl

from macblock.constants import (
    APP_LABEL,
    DNSMASQ_LISTEN_ADDR,
    DNSMASQ_LISTEN_ADDR_V6,
    DNSMASQ_LISTEN_PORT,
    DNSMASQ_USER,
    PF_ANCHOR_FILE,
    PF_CONF,
    PF_EXCLUDE_INTERFACES_FILE,
    PF_LOCK_FILE,
    VAR_DB_UPSTREAM_CONF,
)
from macblock.errors import MacblockError
from macblock.exec import run
from macblock.fs import atomic_write_text


_MARKER_BEGIN = "# macblock begin"
_MARKER_END = "# macblock end"


@contextmanager
def _pf_lock() -> Iterator[None]:
    PF_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PF_LOCK_FILE, "a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass


_iface_re = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")


def _read_excluded_interfaces() -> list[str]:
    if not PF_EXCLUDE_INTERFACES_FILE.exists():
        return []

    out: list[str] = []
    for raw in PF_EXCLUDE_INTERFACES_FILE.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if not _iface_re.match(s):
            continue
        if s not in out:
            out.append(s)
    return out


def _read_upstream_nameserver_ips() -> tuple[list[str], list[str]]:
    if not VAR_DB_UPSTREAM_CONF.exists():
        return [], []

    v4: set[str] = set()
    v6: set[str] = set()

    for raw in VAR_DB_UPSTREAM_CONF.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if not s.startswith("server="):
            continue

        value = s[len("server=") :].strip()
        if not value:
            continue

        if value.startswith("/"):
            parts = [p for p in value.split("/") if p]
            if not parts:
                continue
            candidate = parts[-1]
        else:
            candidate = value

        candidate = candidate.split("#", 1)[0].split("@", 1)[0].strip()
        if not candidate:
            continue

        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            continue

        if ip.version == 4:
            v4.add(str(ip))
        else:
            v6.add(str(ip))

    return sorted(v4), sorted(v6)


def render_anchor_rules() -> str:
    port = DNSMASQ_LISTEN_PORT
    excluded = _read_excluded_interfaces()
    upstream_v4, upstream_v6 = _read_upstream_nameserver_ips()

    lines: list[str] = []

    for iface in excluded:
        lines.append(f"no rdr on {iface} inet proto {{ udp tcp }} from any to any port 53")
        lines.append(f"no rdr on {iface} inet6 proto {{ udp tcp }} from any to any port 53")

    for ip in upstream_v4:
        lines.append(f"no rdr on egress inet proto {{ udp tcp }} from any to {ip} port 53")

    for ip in upstream_v6:
        lines.append(f"no rdr on egress inet6 proto {{ udp tcp }} from any to {ip} port 53")

    lines.extend(
        [
            f"rdr pass on egress inet proto {{ udp tcp }} from any to any port 53 -> {DNSMASQ_LISTEN_ADDR} port {port}",
            f"rdr pass on egress inet6 proto {{ udp tcp }} from any to any port 53 -> {DNSMASQ_LISTEN_ADDR_V6} port {port}",
        ]
    )

    return "\n".join(lines) + "\n"


def _pfctl(args: list[str]) -> None:
    r = run(["/sbin/pfctl", *args])
    if r.returncode != 0:
        raise MacblockError(r.stderr.strip() or "pfctl failed")


def write_anchor_file() -> None:
    atomic_write_text(PF_ANCHOR_FILE, render_anchor_rules(), mode=0o644)


def _with_pf_block(conf_text: str) -> str:
    target_line = f"rdr-anchor \"{APP_LABEL}\""

    block_insert = [
        f"{_MARKER_BEGIN}\n",
        f"{target_line}\n",
        f"{_MARKER_END}\n",
    ]

    base_text = conf_text
    if _MARKER_BEGIN in base_text and _MARKER_END in base_text:
        start = base_text.index(_MARKER_BEGIN)
        end = base_text.index(_MARKER_END) + len(_MARKER_END)
        if end < len(base_text) and base_text[end : end + 1] == "\n":
            end += 1
        base_text = (base_text[:start] + base_text[end:]).lstrip("\n")

    if target_line in base_text:
        if not base_text.endswith("\n"):
            base_text += "\n"
        return base_text

    if not base_text.endswith("\n"):
        base_text += "\n"

    lines = base_text.splitlines(keepends=True)

    filtering_re = re.compile(r"^(anchor|load\s+anchor|pass|block|match|antispoof)\b")
    first_filtering_idx = len(lines)

    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if filtering_re.match(stripped):
            first_filtering_idx = i
            break

    insert_idx = first_filtering_idx

    for i in range(first_filtering_idx - 1, -1, -1):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("rdr-anchor"):
            insert_idx = i + 1
            break

    new_lines = lines[:insert_idx] + block_insert + lines[insert_idx:]
    new_text = "".join(new_lines)
    if not new_text.endswith("\n"):
        new_text += "\n"
    return new_text


def _ensure_pf_conf_block_locked() -> None:
    st = PF_CONF.stat()
    original = PF_CONF.read_text(encoding="utf-8")
    new_text = _with_pf_block(original)
    if new_text == original:
        return

    tmp = PF_CONF.with_suffix(PF_CONF.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.chmod(tmp, st.st_mode)
    os.chown(tmp, st.st_uid, st.st_gid)
    tmp.replace(PF_CONF)


def ensure_pf_conf_block() -> None:
    with _pf_lock():
        _ensure_pf_conf_block_locked()


def remove_pf_conf_block() -> None:
    with _pf_lock():
        if not PF_CONF.exists():
            return

        conf_text = PF_CONF.read_text(encoding="utf-8")
        if _MARKER_BEGIN not in conf_text or _MARKER_END not in conf_text:
            return

        st = PF_CONF.stat()

        start = conf_text.index(_MARKER_BEGIN)
        end = conf_text.index(_MARKER_END) + len(_MARKER_END)

        new_text = (conf_text[:start] + conf_text[end:]).lstrip("\n")
        if not new_text.endswith("\n"):
            new_text += "\n"

        tmp = PF_CONF.with_suffix(PF_CONF.suffix + ".tmp")
        tmp.write_text(new_text, encoding="utf-8")
        os.chmod(tmp, st.st_mode)
        os.chown(tmp, st.st_uid, st.st_gid)
        tmp.replace(PF_CONF)


def validate_pf_conf() -> None:
    with _pf_lock():
        _pfctl(["-nf", str(PF_CONF)])


def _main_ruleset_has_rdr_anchor() -> bool:
    r = run(["/sbin/pfctl", "-sr"])
    if r.returncode != 0:
        return False
    return f"rdr-anchor \"{APP_LABEL}\"" in r.stdout


def enable_anchor() -> None:
    with _pf_lock():
        _ensure_pf_conf_block_locked()
        _pfctl(["-nf", str(PF_CONF)])
        write_anchor_file()

        r = run(["/sbin/pfctl", "-E"])
        if r.returncode not in (0, 1):
            raise MacblockError(r.stderr.strip() or "pfctl -E failed")

        if not _main_ruleset_has_rdr_anchor():
            _pfctl(["-f", str(PF_CONF)])

        _pfctl(["-a", APP_LABEL, "-f", str(PF_ANCHOR_FILE)])


def disable_anchor() -> None:
    with _pf_lock():
        _pfctl(["-a", APP_LABEL, "-F", "all"])


def pf_info() -> str:
    r = run(["/sbin/pfctl", "-s", "info"])
    if r.returncode != 0:
        return r.stderr.strip() or "pfctl failed"
    return r.stdout.strip()


def anchor_rules() -> str:
    r = run(["/sbin/pfctl", "-a", APP_LABEL, "-s", "rules"])
    if r.returncode != 0:
        return r.stderr.strip() or "pfctl failed"
    return r.stdout.strip()
