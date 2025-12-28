from __future__ import annotations

import os
import signal
import time

from macblock.constants import (
    APP_LABEL,
    LAUNCHD_DAEMON_PLIST,
    LAUNCHD_DNSMASQ_PLIST,
    SYSTEM_STATE_FILE,
    SYSTEM_UPSTREAM_FALLBACKS_FILE,
    VAR_DB_DAEMON_PID,
    VAR_DB_DAEMON_READY,
)
from macblock.errors import MacblockError
from macblock.launchd import kickstart
from macblock.state import load_state, replace_state, save_state_atomic
from macblock.resolvers import (
    parse_fallback_upstreams,
    read_fallback_upstreams,
    render_fallback_upstreams,
)
from macblock.system_dns import compute_managed_services, get_dns_servers
from macblock.ui import (
    Spinner,
    header,
    list_item,
    result_success,
    status_info,
    status_warn,
    subheader,
    step_warn,
)


DEFAULT_TIMEOUT = 10.0
RETRY_DELAY = 0.5


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


def _is_process_running(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _read_daemon_pid() -> int | None:
    if not VAR_DB_DAEMON_PID.exists():
        return None
    try:
        pid = int(VAR_DB_DAEMON_PID.read_text(encoding="utf-8").strip())
        return pid if pid > 1 else None
    except Exception:
        return None


def _signal_daemon() -> bool:
    pid = _read_daemon_pid()
    if pid is None:
        return False

    if not _is_process_running(pid):
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
        time.sleep(0.5)
        return _signal_daemon()
    except Exception:
        return False


def _wait_for_daemon_ready(timeout: float = DEFAULT_TIMEOUT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if VAR_DB_DAEMON_READY.exists():
            pid = _read_daemon_pid()
            if pid and _is_process_running(pid):
                return True
        time.sleep(RETRY_DELAY)
    return False


def _wait_for_dns_localhost(timeout: float = DEFAULT_TIMEOUT) -> tuple[bool, list[str]]:
    managed = compute_managed_services()
    if not managed:
        return True, []

    deadline = time.time() + timeout
    failed_services: list[str] = []

    while time.time() < deadline:
        failed_services = []
        for info in managed:
            dns = get_dns_servers(info.name)
            if dns != ["127.0.0.1"]:
                failed_services.append(info.name)

        if not failed_services:
            return True, []

        time.sleep(RETRY_DELAY)

    return False, failed_services


def _wait_for_dns_restored(timeout: float = DEFAULT_TIMEOUT) -> tuple[bool, list[str]]:
    managed = compute_managed_services()
    if not managed:
        return True, []

    deadline = time.time() + timeout
    still_localhost: list[str] = []

    while time.time() < deadline:
        still_localhost = []
        for info in managed:
            dns = get_dns_servers(info.name)
            if dns == ["127.0.0.1"]:
                still_localhost.append(info.name)

        if not still_localhost:
            return True, []

        time.sleep(RETRY_DELAY)

    return False, still_localhost


def do_enable() -> int:
    _check_installed()
    print()

    st = load_state(SYSTEM_STATE_FILE)

    with Spinner("Enabling blocking") as spinner:
        save_state_atomic(
            SYSTEM_STATE_FILE,
            replace_state(st, enabled=True, resume_at_epoch=None),
        )

        if not _trigger_daemon():
            spinner.warn("Could not signal daemon")

        if not _wait_for_daemon_ready(timeout=5.0):
            pass

        dns_ok, failed = _wait_for_dns_localhost(timeout=DEFAULT_TIMEOUT)
        if not dns_ok:
            spinner.fail(f"DNS not redirected for: {', '.join(failed)}")
            step_warn("Run 'macblock doctor' for diagnostics")
            return 1

        spinner.succeed("Blocking enabled")

    result_success("DNS blocking is now active")
    print()
    return 0


def do_disable() -> int:
    _check_installed()
    print()

    st = load_state(SYSTEM_STATE_FILE)

    with Spinner("Disabling blocking") as spinner:
        save_state_atomic(
            SYSTEM_STATE_FILE,
            replace_state(st, enabled=False, resume_at_epoch=None),
        )

        if not _trigger_daemon():
            spinner.warn("Could not signal daemon")

        dns_ok, still_localhost = _wait_for_dns_restored(timeout=DEFAULT_TIMEOUT)
        if not dns_ok:
            spinner.fail(f"DNS not restored for: {', '.join(still_localhost)}")
            step_warn("Run 'macblock doctor' for diagnostics")
            return 1

        spinner.succeed("Blocking disabled")

    result_success("DNS restored to original settings")
    print()
    return 0


def do_pause(duration: str) -> int:
    _check_installed()
    print()

    seconds = _parse_duration_seconds(duration)
    resume_at = int(time.time()) + seconds
    mins = seconds // 60

    st = load_state(SYSTEM_STATE_FILE)

    with Spinner(f"Pausing for {mins} minutes") as spinner:
        save_state_atomic(
            SYSTEM_STATE_FILE,
            replace_state(st, enabled=True, resume_at_epoch=resume_at),
        )

        if not _trigger_daemon():
            spinner.warn("Could not signal daemon")

        dns_ok, still_localhost = _wait_for_dns_restored(timeout=DEFAULT_TIMEOUT)
        if not dns_ok:
            spinner.fail(f"DNS not restored for: {', '.join(still_localhost)}")
            step_warn("Run 'macblock doctor' for diagnostics")
            return 1

        spinner.succeed(f"Paused for {mins} minutes")

    result_success(f"Blocking paused - will auto-resume in {mins} minutes")
    print()
    return 0


def do_resume() -> int:
    _check_installed()
    print()

    st = load_state(SYSTEM_STATE_FILE)

    with Spinner("Resuming blocking") as spinner:
        save_state_atomic(
            SYSTEM_STATE_FILE,
            replace_state(st, enabled=True, resume_at_epoch=None),
        )

        if not _trigger_daemon():
            spinner.warn("Could not signal daemon")

        dns_ok, failed = _wait_for_dns_localhost(timeout=DEFAULT_TIMEOUT)
        if not dns_ok:
            spinner.fail(f"DNS not redirected for: {', '.join(failed)}")
            step_warn("Run 'macblock doctor' for diagnostics")
            return 1

        spinner.succeed("Blocking resumed")

    result_success("DNS blocking is now active")
    print()
    return 0


def _atomic_write(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o644)
    except Exception:
        pass


def do_upstreams_fallbacks_list() -> int:
    _check_installed()
    print()

    header("🌐", "macblock upstream fallbacks")
    status_info("Config file", str(SYSTEM_UPSTREAM_FALLBACKS_FILE))

    fallbacks = read_fallback_upstreams(SYSTEM_UPSTREAM_FALLBACKS_FILE)
    if not fallbacks:
        status_warn("Configured", "none (using built-in defaults)")
        print()
        return 0

    subheader("Configured")
    for ip in fallbacks:
        list_item(ip)

    print()
    return 0


def do_upstreams_fallbacks_set(ips: list[str]) -> int:
    _check_installed()
    print()

    header("🌐", "set upstream fallback DNS")
    status_info("Config file", str(SYSTEM_UPSTREAM_FALLBACKS_FILE))

    current = read_fallback_upstreams(SYSTEM_UPSTREAM_FALLBACKS_FILE)
    if current:
        subheader("Current")
        for ip in current:
            list_item(ip)

    desired = parse_fallback_upstreams("\n".join(ips))
    if not desired:
        raw = input("Enter fallback upstream IPs (comma/space separated): ").strip()
        desired = parse_fallback_upstreams(raw)

    if not desired:
        raise MacblockError("no valid IPs provided")

    subheader("New")
    for ip in desired:
        list_item(ip)

    confirm = (
        input("Write these fallbacks and trigger daemon reconcile? [y/N] ")
        .strip()
        .lower()
    )
    if confirm not in {"y", "yes"}:
        print()
        return 0

    with Spinner("Writing fallback config") as spinner:
        try:
            _atomic_write(
                SYSTEM_UPSTREAM_FALLBACKS_FILE, render_fallback_upstreams(desired)
            )
            spinner.succeed("Fallback config written")
        except Exception as e:
            spinner.fail(f"Could not write config: {e}")
            raise

    with Spinner("Triggering daemon") as spinner:
        if _trigger_daemon():
            spinner.succeed("Daemon signaled")
        else:
            spinner.warn("Could not signal daemon")

    result_success("Upstream fallbacks updated")
    print()
    return 0


def do_upstreams_fallbacks_reset() -> int:
    _check_installed()
    print()

    header("🌐", "reset upstream fallback DNS")
    status_info("Config file", str(SYSTEM_UPSTREAM_FALLBACKS_FILE))

    with Spinner("Removing fallback config") as spinner:
        try:
            if SYSTEM_UPSTREAM_FALLBACKS_FILE.exists():
                SYSTEM_UPSTREAM_FALLBACKS_FILE.unlink()
            spinner.succeed("Fallback config removed")
        except Exception as e:
            spinner.fail(f"Could not remove config: {e}")
            raise

    with Spinner("Triggering daemon") as spinner:
        if _trigger_daemon():
            spinner.succeed("Daemon signaled")
        else:
            spinner.warn("Could not signal daemon")

    result_success("Upstream fallbacks reset")
    print()
    return 0
