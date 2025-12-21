from __future__ import annotations

import time

from macblock.colors import print_success
from macblock.constants import (
    APP_LABEL,
    LAUNCHD_DIR,
    LAUNCHD_DNSMASQ_PLIST,
    SYSTEM_STATE_FILE,
)
from macblock.errors import MacblockError
from macblock.launchd import bootstrap_system, enable_service, kickstart
from macblock.state import load_state, replace_state, save_state_atomic


def _parse_duration_seconds(value: str) -> int:
    value = value.strip().lower()
    if value.endswith("m"):
        return int(value[:-1]) * 60
    if value.endswith("h"):
        return int(value[:-1]) * 60 * 60
    if value.endswith("d"):
        return int(value[:-1]) * 60 * 60 * 24
    raise ValueError("duration must end with m/h/d")


def _ensure_daemon(plist, label: str) -> None:
    try:
        bootstrap_system(plist)
    except Exception:
        pass

    try:
        enable_service(label)
    except Exception:
        pass

    try:
        kickstart(label)
    except Exception:
        pass


def _ensure_daemons() -> None:
    daemon_plist = LAUNCHD_DIR / f"{APP_LABEL}.daemon.plist"

    if not LAUNCHD_DNSMASQ_PLIST.exists() or not daemon_plist.exists():
        raise MacblockError("macblock is not installed; run: sudo macblock install")

    _ensure_daemon(LAUNCHD_DNSMASQ_PLIST, f"{APP_LABEL}.dnsmasq")
    _ensure_daemon(daemon_plist, f"{APP_LABEL}.daemon")


def _kickstart_daemon() -> None:
    try:
        kickstart(f"{APP_LABEL}.daemon")
    except Exception:
        pass


def do_enable() -> int:
    _ensure_daemons()
    st = load_state(SYSTEM_STATE_FILE)

    save_state_atomic(
        SYSTEM_STATE_FILE,
        replace_state(st, enabled=True, resume_at_epoch=None),
    )
    _kickstart_daemon()

    print_success("enabled")
    return 0


def do_disable() -> int:
    _ensure_daemons()
    st = load_state(SYSTEM_STATE_FILE)

    save_state_atomic(
        SYSTEM_STATE_FILE,
        replace_state(st, enabled=False, resume_at_epoch=None),
    )
    _kickstart_daemon()

    print_success("disabled")
    return 0


def do_pause(duration: str) -> int:
    _ensure_daemons()
    seconds = _parse_duration_seconds(duration)
    resume_at = int(time.time()) + seconds

    st = load_state(SYSTEM_STATE_FILE)
    save_state_atomic(
        SYSTEM_STATE_FILE,
        replace_state(st, enabled=True, resume_at_epoch=resume_at),
    )
    _kickstart_daemon()

    print_success("paused")
    return 0


def do_resume() -> int:
    _ensure_daemons()
    st = load_state(SYSTEM_STATE_FILE)

    save_state_atomic(
        SYSTEM_STATE_FILE,
        replace_state(st, enabled=True, resume_at_epoch=None),
    )
    _kickstart_daemon()

    print_success("resumed")
    return 0
