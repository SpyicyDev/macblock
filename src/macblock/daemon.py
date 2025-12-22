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


def _handle_sigusr1(signum: int, frame: object) -> None:
    global _trigger_apply
    _trigger_apply = True


def _is_forward_ip(ip: str) -> bool:
    if not ip:
        return False
    if ip in {"127.0.0.1", "::1", "0.0.0.0", "::"}:
        return False
    return True


def _hup_dnsmasq() -> None:
    if not VAR_DB_DNSMASQ_PID.exists():
        return

    try:
        pid = int(VAR_DB_DNSMASQ_PID.read_text(encoding="utf-8").strip())
    except Exception:
        return

    if pid <= 1:
        return

    try:
        os.kill(pid, signal.SIGHUP)
    except (ProcessLookupError, PermissionError):
        pass


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


def _enable_blocking(state: State, managed_infos: list) -> State:
    dns_backup = dict(state.dns_backup)
    managed_names: list[str] = []

    for info in managed_infos:
        managed_names.append(info.name)
        _backup_service_dns(info.name, info.device, dns_backup)
        set_dns_servers(info.name, ["127.0.0.1"])

    return replace_state(
        state,
        dns_backup=dns_backup,
        managed_services=managed_names,
    )


def _disable_blocking(state: State, managed_names: list[str]) -> None:
    to_restore = state.managed_services if state.managed_services else managed_names

    for service in to_restore:
        backup_data = state.dns_backup.get(service)
        if not isinstance(backup_data, dict):
            continue

        dns = backup_data.get("dns")
        search = backup_data.get("search")

        set_dns_servers(service, list(dns) if isinstance(dns, list) else None)
        set_search_domains(service, list(search) if isinstance(search, list) else None)


def _apply_state() -> None:
    state = load_state(SYSTEM_STATE_FILE)

    now = int(time.time())
    paused = state.resume_at_epoch is not None and state.resume_at_epoch > now

    if state.resume_at_epoch is not None and state.resume_at_epoch <= now:
        state = replace_state(state, resume_at_epoch=None)

    exclude = _load_exclude_services()
    managed_infos = compute_managed_services(exclude=exclude)
    managed_names = [info.name for info in managed_infos]

    if state.enabled and not paused:
        state = _enable_blocking(state, managed_infos)
    else:
        _disable_blocking(state, managed_names)

    save_state_atomic(SYSTEM_STATE_FILE, state)
    _update_upstreams(state)
    _hup_dnsmasq()


def _seconds_until_resume(state: State) -> float | None:
    if not state.enabled:
        return None

    if state.resume_at_epoch is None:
        return None

    now = int(time.time())
    if state.resume_at_epoch <= now:
        return 0

    return float(state.resume_at_epoch - now)


def _wait_for_network_change(timeout: float | None) -> None:
    cmd = ["/usr/bin/notifyutil", "-w", "com.apple.system.config.network_change"]

    try:
        subprocess.run(cmd, check=False, timeout=timeout, capture_output=True)
    except subprocess.TimeoutExpired:
        pass


def _write_pid_file() -> None:
    VAR_DB_DAEMON_PID.parent.mkdir(parents=True, exist_ok=True)
    VAR_DB_DAEMON_PID.write_text(f"{os.getpid()}\n", encoding="utf-8")


def _remove_pid_file() -> None:
    try:
        VAR_DB_DAEMON_PID.unlink()
    except Exception:
        pass


def run_daemon() -> int:
    global _trigger_apply

    signal.signal(signal.SIGUSR1, _handle_sigusr1)
    _write_pid_file()

    print(f"macblock daemon started (pid={os.getpid()})", file=sys.stderr)

    try:
        while True:
            _trigger_apply = False

            try:
                _apply_state()
            except Exception as e:
                print(f"error applying state: {e}", file=sys.stderr)

            state = load_state(SYSTEM_STATE_FILE)
            timeout = _seconds_until_resume(state)
            _wait_for_network_change(timeout)

            if _trigger_apply:
                continue

    except KeyboardInterrupt:
        print("daemon interrupted", file=sys.stderr)
        return 0
    finally:
        _remove_pid_file()

    return 0
