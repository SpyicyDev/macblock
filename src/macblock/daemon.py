"""
Daemon entry point for launchd. Run with: macblock daemon
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

from macblock.constants import (
    SYSTEM_DNS_EXCLUDE_SERVICES_FILE,
    SYSTEM_STATE_FILE,
    VAR_DB_DAEMON_PID,
    VAR_DB_DAEMON_READY,
    VAR_DB_DNSMASQ_PID,
    VAR_DB_UPSTREAM_CONF,
)
from macblock.resolvers import read_system_resolvers
from macblock.state import load_state, save_state_atomic, replace_state, State
from macblock.system_dns import (
    compute_managed_services,
    get_dns_servers,
    get_search_domains,
    set_dns_servers,
    set_search_domains,
    parse_exclude_services_file,
    read_dhcp_nameservers,
)


_trigger_apply = False
_shutdown_requested = False


def _handle_sigusr1(signum: int, frame: object) -> None:
    global _trigger_apply
    _trigger_apply = True


def _handle_sigterm(signum: int, frame: object) -> None:
    global _shutdown_requested
    _shutdown_requested = True


def _is_forward_ip(ip: str) -> bool:
    if not ip:
        return False
    if ip in {"127.0.0.1", "::1", "0.0.0.0", "::"}:
        return False
    return True


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


def _read_pid_file(path) -> int | None:
    if not path.exists():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
        return pid if pid > 1 else None
    except Exception:
        return None


def _hup_dnsmasq() -> bool:
    pid = _read_pid_file(VAR_DB_DNSMASQ_PID)
    if pid is None:
        return False

    if not _is_process_running(pid):
        print(f"dnsmasq pid {pid} not running, removing stale pid file", file=sys.stderr)
        try:
            VAR_DB_DNSMASQ_PID.unlink()
        except Exception:
            pass
        return False

    try:
        os.kill(pid, signal.SIGHUP)
        return True
    except (ProcessLookupError, PermissionError) as e:
        print(f"failed to HUP dnsmasq: {e}", file=sys.stderr)
        return False


def _load_exclude_services() -> set[str]:
    if not SYSTEM_DNS_EXCLUDE_SERVICES_FILE.exists():
        return set()

    try:
        text = SYSTEM_DNS_EXCLUDE_SERVICES_FILE.read_text(encoding="utf-8")
        return parse_exclude_services_file(text)
    except Exception:
        return set()


def _collect_upstream_defaults(state: State, exclude: set[str]) -> list[str]:
    defaults: list[str] = []

    resolvers = read_system_resolvers()
    for ip in resolvers.defaults:
        if _is_forward_ip(ip) and ip not in defaults:
            defaults.append(ip)

    for info in compute_managed_services(exclude=exclude):
        for ip in read_dhcp_nameservers(info.device or ""):
            if _is_forward_ip(ip) and ip not in defaults:
                defaults.append(ip)

    for service, backup_data in state.dns_backup.items():
        if not isinstance(backup_data, dict):
            continue

        dns_servers = backup_data.get("dns")
        if isinstance(dns_servers, list):
            for ip in dns_servers:
                if isinstance(ip, str) and _is_forward_ip(ip) and ip not in defaults:
                    defaults.append(ip)

        dhcp_servers = backup_data.get("dhcp")
        if isinstance(dhcp_servers, list):
            for ip in dhcp_servers:
                if isinstance(ip, str) and _is_forward_ip(ip) and ip not in defaults:
                    defaults.append(ip)

    if not defaults:
        defaults = ["1.1.1.1", "8.8.8.8"]

    return defaults


def _update_upstreams(state: State) -> None:
    exclude = _load_exclude_services()
    defaults = _collect_upstream_defaults(state, exclude)
    resolvers = read_system_resolvers()

    lines: list[str] = []
    for ip in defaults:
        lines.append(f"server={ip}")

    for domain, ips in sorted(resolvers.per_domain.items()):
        for ip in ips:
            if _is_forward_ip(ip):
                lines.append(f"server=/{domain}/{ip}")

    conf_text = "\n".join(lines) + "\n"

    VAR_DB_UPSTREAM_CONF.parent.mkdir(parents=True, exist_ok=True)
    tmp = VAR_DB_UPSTREAM_CONF.with_suffix(".tmp")
    tmp.write_text(conf_text, encoding="utf-8")
    tmp.replace(VAR_DB_UPSTREAM_CONF)


def _backup_service_dns(service: str, device: str | None, dns_backup: dict) -> None:
    if service in dns_backup:
        return

    current_dns = get_dns_servers(service)
    if current_dns == ["127.0.0.1"]:
        return

    dhcp = read_dhcp_nameservers(device or "")
    dns_backup[service] = {
        "dns": current_dns,
        "search": get_search_domains(service),
        "dhcp": dhcp or None,
    }


def _enable_blocking(state: State, managed_infos: list) -> tuple[State, list[str]]:
    dns_backup = dict(state.dns_backup)
    managed_names: list[str] = []
    failures: list[str] = []

    for info in managed_infos:
        managed_names.append(info.name)
        _backup_service_dns(info.name, info.device, dns_backup)
        if not set_dns_servers(info.name, ["127.0.0.1"]):
            failures.append(f"failed to set DNS for {info.name}")

    new_state = replace_state(
        state,
        dns_backup=dns_backup,
        managed_services=managed_names,
    )
    return new_state, failures


def _disable_blocking(state: State, managed_names: list[str]) -> list[str]:
    to_restore = state.managed_services if state.managed_services else managed_names
    failures: list[str] = []

    for service in to_restore:
        backup_data = state.dns_backup.get(service)
        if not isinstance(backup_data, dict):
            continue

        dns = backup_data.get("dns")
        search = backup_data.get("search")

        if not set_dns_servers(service, list(dns) if isinstance(dns, list) else None):
            failures.append(f"failed to restore DNS for {service}")
        if not set_search_domains(service, list(search) if isinstance(search, list) else None):
            failures.append(f"failed to restore search domains for {service}")

    return failures


def _verify_dns_state(state: State, managed_infos: list, should_be_localhost: bool) -> list[str]:
    issues: list[str] = []
    for info in managed_infos:
        current = get_dns_servers(info.name)
        if should_be_localhost:
            if current != ["127.0.0.1"]:
                issues.append(f"{info.name}: expected 127.0.0.1, got {current}")
        else:
            if current == ["127.0.0.1"]:
                issues.append(f"{info.name}: still pointing to localhost")
    return issues


def _apply_state() -> tuple[bool, list[str]]:
    state = load_state(SYSTEM_STATE_FILE)
    issues: list[str] = []

    now = int(time.time())
    paused = state.resume_at_epoch is not None and state.resume_at_epoch > now

    if state.resume_at_epoch is not None and state.resume_at_epoch <= now:
        state = replace_state(state, resume_at_epoch=None)

    exclude = _load_exclude_services()
    managed_infos = compute_managed_services(exclude=exclude)
    managed_names = [info.name for info in managed_infos]

    if state.enabled and not paused:
        state, failures = _enable_blocking(state, managed_infos)
        issues.extend(failures)
        should_be_localhost = True
    else:
        failures = _disable_blocking(state, managed_names)
        issues.extend(failures)
        should_be_localhost = False

    save_state_atomic(SYSTEM_STATE_FILE, state)
    _update_upstreams(state)
    _hup_dnsmasq()

    time.sleep(0.1)
    verification_issues = _verify_dns_state(state, managed_infos, should_be_localhost)
    issues.extend(verification_issues)

    return len(issues) == 0, issues


def _seconds_until_resume(state: State) -> float | None:
    if not state.enabled:
        return None

    if state.resume_at_epoch is None:
        return None

    now = int(time.time())
    if state.resume_at_epoch <= now:
        return 0

    return float(state.resume_at_epoch - now)


def _wait_for_network_change_or_signal(timeout: float | None) -> None:
    """Wait for network change notification or until signaled.
    
    Uses Popen with a poll loop so we can check for signals.
    """
    global _trigger_apply, _shutdown_requested
    
    cmd = ["/usr/bin/notifyutil", "-w", "com.apple.system.config.network_change"]
    
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        # If we can't start notifyutil, just sleep briefly
        time.sleep(1.0)
        return
    
    try:
        deadline = time.time() + timeout if timeout else None
        poll_interval = 0.25  # Check for signals every 250ms
        
        while True:
            # Check if we should exit the wait
            if _trigger_apply or _shutdown_requested:
                break
            
            # Check if timeout expired
            if deadline and time.time() >= deadline:
                break
            
            # Check if process finished (network change occurred)
            ret = proc.poll()
            if ret is not None:
                break
            
            # Sleep briefly before next poll
            time.sleep(poll_interval)
    finally:
        # Clean up the subprocess
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def _write_pid_file() -> None:
    VAR_DB_DAEMON_PID.parent.mkdir(parents=True, exist_ok=True)
    VAR_DB_DAEMON_PID.write_text(f"{os.getpid()}\n", encoding="utf-8")


def _write_ready_file() -> None:
    VAR_DB_DAEMON_READY.parent.mkdir(parents=True, exist_ok=True)
    VAR_DB_DAEMON_READY.write_text(f"{int(time.time())}\n", encoding="utf-8")


def _remove_pid_file() -> None:
    try:
        VAR_DB_DAEMON_PID.unlink()
    except Exception:
        pass


def _remove_ready_file() -> None:
    try:
        VAR_DB_DAEMON_READY.unlink()
    except Exception:
        pass


def _check_stale_daemon() -> bool:
    pid = _read_pid_file(VAR_DB_DAEMON_PID)
    if pid is None:
        return False

    if pid == os.getpid():
        return False

    if _is_process_running(pid):
        print(f"another daemon is already running (pid={pid})", file=sys.stderr)
        return True

    print(f"removing stale pid file (pid={pid} not running)", file=sys.stderr)
    _remove_pid_file()
    _remove_ready_file()
    return False


def run_daemon() -> int:
    global _trigger_apply, _shutdown_requested

    if _check_stale_daemon():
        return 1

    signal.signal(signal.SIGUSR1, _handle_sigusr1)
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    _write_pid_file()

    print(f"macblock daemon started (pid={os.getpid()})", file=sys.stderr)

    consecutive_failures = 0
    max_consecutive_failures = 5

    try:
        while not _shutdown_requested:
            _trigger_apply = False

            try:
                success, issues = _apply_state()
                if success:
                    consecutive_failures = 0
                    if not VAR_DB_DAEMON_READY.exists():
                        _write_ready_file()
                        print("daemon ready", file=sys.stderr)
                else:
                    consecutive_failures += 1
                    for issue in issues:
                        print(f"state apply issue: {issue}", file=sys.stderr)

                    if consecutive_failures >= max_consecutive_failures:
                        print(f"too many consecutive failures ({consecutive_failures}), continuing anyway", file=sys.stderr)
                        consecutive_failures = 0

            except Exception as e:
                consecutive_failures += 1
                print(f"error applying state: {e}", file=sys.stderr)

                if consecutive_failures >= max_consecutive_failures:
                    print(f"too many consecutive failures ({consecutive_failures}), continuing anyway", file=sys.stderr)
                    consecutive_failures = 0

            if _shutdown_requested:
                break

            state = load_state(SYSTEM_STATE_FILE)
            timeout = _seconds_until_resume(state)

            if timeout is not None and timeout > 60:
                timeout = 60.0

            _wait_for_network_change_or_signal(timeout)

    except KeyboardInterrupt:
        print("daemon interrupted", file=sys.stderr)
    finally:
        print("daemon shutting down", file=sys.stderr)
        _remove_ready_file()
        _remove_pid_file()

    return 0
