from __future__ import annotations

import os
import signal
import time

from macblock.colors import print_info, print_success, print_warning
from macblock.constants import (
    APP_LABEL,
    LAUNCHD_DAEMON_PLIST,
    LAUNCHD_DNSMASQ_PLIST,
    SYSTEM_STATE_FILE,
    VAR_DB_DAEMON_PID,
)
from macblock.errors import MacblockError
from macblock.launchd import kickstart
from macblock.state import load_state, replace_state, save_state_atomic
from macblock.system_dns import compute_managed_services, get_dns_servers


def _parse_duration_seconds(value: str) -> int:
    value = value.strip().lower()
    if value.endswith("m"):
        return int(value[:-1]) * 60
    if value.endswith("h"):
        return int(value[:-1]) * 60 * 60
    if value.endswith("d"):
        return int(value[:-1]) * 60 * 60 * 24
    raise ValueError("duration must end with m/h/d")


def _check_installed() -> None:
    if not LAUNCHD_DNSMASQ_PLIST.exists() or not LAUNCHD_DAEMON_PLIST.exists():
        raise MacblockError("macblock is not installed; run: sudo macblock install")


def _signal_daemon() -> bool:
    if not VAR_DB_DAEMON_PID.exists():
        return False

    try:
        pid = int(VAR_DB_DAEMON_PID.read_text(encoding="utf-8").strip())
    except Exception:
        return False

    if pid <= 1:
        return False

    try:
        os.kill(pid, signal.SIGUSR1)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return False


def _trigger_daemon() -> bool:
    if _signal_daemon():
        return True

    try:
        kickstart(f"{APP_LABEL}.daemon")
        return True
    except Exception:
        return False


def _wait_for_dns_localhost(timeout: float = 3.0) -> bool:
    managed = compute_managed_services()
    if not managed:
        return True

    deadline = time.time() + timeout
    while time.time() < deadline:
        all_localhost = True
        for info in managed:
            dns = get_dns_servers(info.name)
            if dns != ["127.0.0.1"]:
                all_localhost = False
                break
        if all_localhost:
            return True
        time.sleep(0.3)

    return False


def _wait_for_dns_restored(timeout: float = 3.0) -> bool:
    managed = compute_managed_services()
    if not managed:
        return True

    deadline = time.time() + timeout
    while time.time() < deadline:
        all_restored = True
        for info in managed:
            dns = get_dns_servers(info.name)
            if dns == ["127.0.0.1"]:
                all_restored = False
                break
        if all_restored:
            return True
        time.sleep(0.3)

    return False


def do_enable() -> int:
    _check_installed()
    st = load_state(SYSTEM_STATE_FILE)

    save_state_atomic(
        SYSTEM_STATE_FILE,
        replace_state(st, enabled=True, resume_at_epoch=None),
    )

    if not _trigger_daemon():
        print_warning("could not signal daemon")

    if not _wait_for_dns_localhost():
        print_warning("DNS may not have been redirected yet; check 'macblock doctor'")

    print_success("enabled")
    return 0


def do_disable() -> int:
    _check_installed()
    st = load_state(SYSTEM_STATE_FILE)

    save_state_atomic(
        SYSTEM_STATE_FILE,
        replace_state(st, enabled=False, resume_at_epoch=None),
    )

    if not _trigger_daemon():
        print_warning("could not signal daemon")

    if not _wait_for_dns_restored():
        print_warning("DNS may not have been restored yet; check 'macblock doctor'")

    print_success("disabled")
    return 0


def do_pause(duration: str) -> int:
    _check_installed()
    seconds = _parse_duration_seconds(duration)
    resume_at = int(time.time()) + seconds

    st = load_state(SYSTEM_STATE_FILE)
    save_state_atomic(
        SYSTEM_STATE_FILE,
        replace_state(st, enabled=True, resume_at_epoch=resume_at),
    )

    if not _trigger_daemon():
        print_warning("could not signal daemon")

    if not _wait_for_dns_restored():
        print_warning("DNS may not have been restored yet; check 'macblock doctor'")

    mins = seconds // 60
    print_info(f"paused for {mins} minutes")
    print_success("paused")
    return 0


def do_resume() -> int:
    _check_installed()
    st = load_state(SYSTEM_STATE_FILE)

    save_state_atomic(
        SYSTEM_STATE_FILE,
        replace_state(st, enabled=True, resume_at_epoch=None),
    )

    if not _trigger_daemon():
        print_warning("could not signal daemon")

    if not _wait_for_dns_localhost():
        print_warning("DNS may not have been redirected yet; check 'macblock doctor'")

    print_success("resumed")
    return 0
