"""
Daemon entry point for launchd. Run with: macblock daemon
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time

from macblock.constants import (
    SYSTEM_DNS_EXCLUDE_SERVICES_FILE,
    SYSTEM_STATE_FILE,
    VAR_DB_DAEMON_PID,
    VAR_DB_DAEMON_READY,
    VAR_DB_DAEMON_LAST_APPLY,
    VAR_DB_DNSMASQ_PID,
    VAR_DB_UPSTREAM_CONF,
)
from macblock.exec import run
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


def _log(message: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", file=sys.stderr, flush=True)


def _write_last_apply_file() -> None:
    VAR_DB_DAEMON_LAST_APPLY.parent.mkdir(parents=True, exist_ok=True)
    VAR_DB_DAEMON_LAST_APPLY.write_text(f"{int(time.time())}\n", encoding="utf-8")


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


_IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")


def _get_default_route_interface() -> str | None:
    r = run(["/sbin/route", "-n", "get", "default"], timeout=2.0)
    if r.returncode != 0:
        return None

    for raw in r.stdout.splitlines():
        line = raw.strip()
        if not line.startswith("interface:"):
            continue
        interface = line.split(":", 1)[1].strip()
        return interface or None

    return None


def _get_interface_ipv4(interface: str) -> str | None:
    if not interface:
        return None

    r = run(["/usr/sbin/ipconfig", "getifaddr", interface], timeout=2.0)
    if r.returncode != 0:
        return None

    ip = (r.stdout or "").strip()
    return ip if _IPV4_RE.match(ip) else None


def _network_ready() -> tuple[bool, str, str | None, str | None]:
    interface = _get_default_route_interface()
    if not interface:
        return False, "no default route", None, None

    ip = _get_interface_ipv4(interface)
    if not ip:
        return False, f"no IPv4 for {interface}", interface, None

    return True, "", interface, ip


def _wait_for_network_ready(max_wait_s: float = 15.0) -> bool:
    start = time.time()
    stable_good: tuple[str, str] | None = None
    stable_count = 0

    logged_start = False
    last_reason: str | None = None

    while True:
        now = time.time()
        elapsed = now - start

        if _shutdown_requested or _trigger_apply:
            return False

        if elapsed >= max_wait_s:
            if logged_start:
                print(
                    f"network not ready after {max_wait_s:.0f}s; applying anyway",
                    file=sys.stderr,
                )
            return False

        ready, reason, interface, ip = _network_ready()
        if ready and interface and ip:
            current = (interface, ip)
            if current == stable_good:
                stable_count += 1
            else:
                stable_good = current
                stable_count = 1

            if stable_count >= 2:
                if elapsed >= 0.25:
                    print(
                        f"network ready after {elapsed:.1f}s ({interface} {ip})",
                        file=sys.stderr,
                    )
                return True

        else:
            stable_good = None
            stable_count = 0

            if not logged_start:
                print(
                    f"waiting for network ready (max {max_wait_s:.0f}s): {reason}",
                    file=sys.stderr,
                )
                logged_start = True
                last_reason = reason
            elif reason != last_reason and elapsed >= 1.0:
                print(f"waiting for network ready: {reason}", file=sys.stderr)
                last_reason = reason

        time.sleep(0.25)


def _hup_dnsmasq() -> bool:
    pid = _read_pid_file(VAR_DB_DNSMASQ_PID)
    if pid is None:
        return False

    if not _is_process_running(pid):
        print(
            f"dnsmasq pid {pid} not running, removing stale pid file", file=sys.stderr
        )
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


def _update_upstreams(state: State) -> bool:
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

    try:
        if VAR_DB_UPSTREAM_CONF.exists():
            existing = VAR_DB_UPSTREAM_CONF.read_text(
                encoding="utf-8", errors="replace"
            )
            if existing == conf_text:
                return False
    except Exception:
        pass

    VAR_DB_UPSTREAM_CONF.parent.mkdir(parents=True, exist_ok=True)
    tmp = VAR_DB_UPSTREAM_CONF.with_suffix(".tmp")
    tmp.write_text(conf_text, encoding="utf-8")
    tmp.replace(VAR_DB_UPSTREAM_CONF)
    return True


def _backup_service_dns(
    service: str,
    device: str | None,
    dns_backup: dict,
    *,
    current_dns: list[str] | None,
) -> None:
    if service in dns_backup:
        return

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

        current_dns = get_dns_servers(info.name)
        _backup_service_dns(info.name, info.device, dns_backup, current_dns=current_dns)

        if current_dns == ["127.0.0.1"]:
            _log(f"apply: {info.name}: DNS already 127.0.0.1")
            continue

        if set_dns_servers(info.name, ["127.0.0.1"]):
            _log(f"apply: {info.name}: set DNS -> 127.0.0.1")
        else:
            failures.append(f"failed to set DNS for {info.name}")
            _log(f"apply: {info.name}: failed to set DNS -> 127.0.0.1")

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
            _log(f"apply: {service}: no DNS backup found; skipping restore")
            continue

        dns = backup_data.get("dns")
        search = backup_data.get("search")

        desired_dns = list(dns) if isinstance(dns, list) else None
        desired_search = list(search) if isinstance(search, list) else None

        current_dns = get_dns_servers(service)
        if current_dns == desired_dns:
            _log(f"apply: {service}: DNS already restored")
        else:
            if set_dns_servers(service, desired_dns):
                _log(f"apply: {service}: restored DNS -> {desired_dns}")
            else:
                failures.append(f"failed to restore DNS for {service}")
                _log(f"apply: {service}: failed to restore DNS -> {desired_dns}")

        current_search = get_search_domains(service)
        if current_search == desired_search:
            _log(f"apply: {service}: search domains already restored")
        else:
            if set_search_domains(service, desired_search):
                _log(f"apply: {service}: restored search domains -> {desired_search}")
            else:
                failures.append(f"failed to restore search domains for {service}")
                _log(
                    f"apply: {service}: failed to restore search domains -> {desired_search}"
                )

    return failures


def _verify_dns_state(
    state: State, managed_infos: list, should_be_localhost: bool
) -> list[str]:
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


def _apply_state(*, reason: str = "unknown") -> tuple[bool, list[str]]:
    started = time.time()

    state = load_state(SYSTEM_STATE_FILE)
    issues: list[str] = []

    now = int(time.time())
    paused = state.resume_at_epoch is not None and state.resume_at_epoch > now

    if state.resume_at_epoch is not None and state.resume_at_epoch <= now:
        state = replace_state(state, resume_at_epoch=None)

    exclude = _load_exclude_services()
    managed_infos = compute_managed_services(exclude=exclude)
    managed_names = [info.name for info in managed_infos]

    _log(
        f"apply start (reason={reason}) enabled={state.enabled} paused={paused} managed={len(managed_names)}"
    )
    if managed_names:
        _log("apply: managed services: " + ", ".join(managed_names))
    else:
        _log("apply: no managed services detected")

    if state.enabled and not paused:
        _log("apply: enforcing localhost DNS (127.0.0.1)")
        state, failures = _enable_blocking(state, managed_infos)
        issues.extend(failures)
        should_be_localhost = True
    else:
        _log("apply: restoring DNS from backup")
        failures = _disable_blocking(state, managed_names)
        issues.extend(failures)
        should_be_localhost = False

    save_state_atomic(SYSTEM_STATE_FILE, state)

    upstreams_changed = _update_upstreams(state)
    if upstreams_changed:
        _log("apply: upstreams updated; reloading dnsmasq")
        if _hup_dnsmasq():
            _log("apply: dnsmasq reload signal sent")
        else:
            _log("apply: failed to reload dnsmasq")
    else:
        _log("apply: upstreams unchanged; skipping dnsmasq reload")

    time.sleep(0.1)
    verification_issues = _verify_dns_state(state, managed_infos, should_be_localhost)
    issues.extend(verification_issues)

    if verification_issues:
        for issue in verification_issues:
            _log(f"apply: verify issue: {issue}")

    elapsed = time.time() - started
    ok = len(issues) == 0
    if ok:
        _log(f"apply done: success ({elapsed:.2f}s)")
    else:
        _log(f"apply done: {len(issues)} issue(s) ({elapsed:.2f}s)")

    return ok, issues


def _seconds_until_resume(state: State) -> float | None:
    if not state.enabled:
        return None

    if state.resume_at_epoch is None:
        return None

    now = int(time.time())
    if state.resume_at_epoch <= now:
        return 0

    return float(state.resume_at_epoch - now)


def _should_wait_for_network_before_apply(state: State) -> bool:
    if not state.enabled:
        return False

    now = int(time.time())
    paused = state.resume_at_epoch is not None and state.resume_at_epoch > now
    return not paused


def _wait_for_network_change_or_signal(
    timeout: float | None,
) -> tuple[str, int | None]:
    """Wait for network change notification or until signaled.

    Uses Popen with a poll loop so we can check for signals.
    """
    global _trigger_apply, _shutdown_requested

    cmd = ["/usr/bin/notifyutil", "-1", "com.apple.system.config.network_change"]

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        time.sleep(1.0)
        return "sleep", None

    reason: str = "timeout"
    exit_code: int | None = None

    try:
        deadline = time.time() + timeout if timeout is not None else None
        poll_interval = 0.25

        while True:
            if _shutdown_requested:
                reason = "shutdown"
                break

            if _trigger_apply:
                reason = "signal"
                break

            if deadline is not None and time.time() >= deadline:
                reason = "timeout"
                break

            ret = proc.poll()
            if ret is not None:
                reason = "notify"
                exit_code = ret
                break

            time.sleep(poll_interval)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    return reason, exit_code


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

    _log(f"macblock daemon started (pid={os.getpid()})")

    consecutive_failures = 0
    max_consecutive_failures = 5

    wake_reason = "startup"

    try:
        while not _shutdown_requested:
            _trigger_apply = False

            state_for_wait = load_state(SYSTEM_STATE_FILE)
            if _should_wait_for_network_before_apply(state_for_wait):
                _wait_for_network_ready(15.0)

            try:
                success, issues = _apply_state(reason=wake_reason)
                if success:
                    consecutive_failures = 0
                    _write_last_apply_file()

                    if not VAR_DB_DAEMON_READY.exists():
                        _write_ready_file()
                        _log("daemon ready")
                else:
                    consecutive_failures += 1
                    _log(f"apply returned {len(issues)} issue(s)")

                    if consecutive_failures >= max_consecutive_failures:
                        _log(
                            f"too many consecutive failures ({consecutive_failures}), continuing anyway"
                        )
                        consecutive_failures = 0

            except Exception as e:
                consecutive_failures += 1
                _log(f"error applying state: {e}")

                if consecutive_failures >= max_consecutive_failures:
                    _log(
                        f"too many consecutive failures ({consecutive_failures}), continuing anyway"
                    )
                    consecutive_failures = 0

            if _shutdown_requested:
                break

            state = load_state(SYSTEM_STATE_FILE)
            timeout = _seconds_until_resume(state)

            if timeout is None:
                timeout = 300.0
            elif timeout > 60:
                timeout = 60.0

            _log(f"waiting for network changes (timeout={timeout:.0f}s)")
            wait_reason, exit_code = _wait_for_network_change_or_signal(timeout)

            if wait_reason == "shutdown":
                wake_reason = "shutdown"
            elif wait_reason == "signal":
                _log("wake: received SIGUSR1 trigger")
                wake_reason = "signal"
            elif wait_reason == "notify":
                _log(f"wake: network change notification (exit_code={exit_code})")
                wake_reason = "notify"
            elif wait_reason == "timeout":
                _log("wake: periodic reconcile")
                wake_reason = "timeout"
            else:
                _log(f"wake: notify watcher fallback ({wait_reason})")
                wake_reason = wait_reason

            if wake_reason == "shutdown":
                break

    except KeyboardInterrupt:
        _log("daemon interrupted")
    finally:
        _log("daemon shutting down")
        _remove_ready_file()
        _remove_pid_file()

    return 0
