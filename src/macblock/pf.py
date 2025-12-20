from __future__ import annotations

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


def render_anchor_rules() -> str:
    port = DNSMASQ_LISTEN_PORT
    user = DNSMASQ_USER
    excluded = _read_excluded_interfaces()

    lines: list[str] = []

    for iface in excluded:
        lines.append(f"no rdr on {iface} inet proto {{ udp tcp }} from any to any port 53")
        lines.append(f"no rdr on {iface} inet6 proto {{ udp tcp }} from any to any port 53")

    lines.extend(
        [
            f"rdr pass on egress inet proto {{ udp tcp }} from any to any port 53 user != {user} -> {DNSMASQ_LISTEN_ADDR} port {port}",
            f"rdr pass on egress inet6 proto {{ udp tcp }} from any to any port 53 user != {user} -> {DNSMASQ_LISTEN_ADDR_V6} port {port}",
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
    block = "\n".join(
        [
            _MARKER_BEGIN,
            f"rdr-anchor \"{APP_LABEL}\"",
            f"anchor \"{APP_LABEL}\"",
            f"load anchor \"{APP_LABEL}\" from \"{PF_ANCHOR_FILE}\"",
            _MARKER_END,
        ]
    )

    if _MARKER_BEGIN in conf_text and _MARKER_END in conf_text:
        start = conf_text.index(_MARKER_BEGIN)
        end = conf_text.index(_MARKER_END) + len(_MARKER_END)
        new_text = conf_text[:start] + block + conf_text[end:]
        if not new_text.endswith("\n"):
            new_text += "\n"
        return new_text

    if not conf_text.endswith("\n"):
        conf_text += "\n"
    return conf_text + "\n" + block + "\n"


def ensure_pf_conf_block() -> None:
    with _pf_lock():
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


def enable_anchor() -> None:
    with _pf_lock():
        write_anchor_file()

        r = run(["/sbin/pfctl", "-E"])
        if r.returncode not in (0, 1):
            raise MacblockError(r.stderr.strip() or "pfctl -E failed")

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
