from __future__ import annotations

import errno
import os
import socket
import time

from macblock import __version__
from macblock.colors import bold, error, info, success, warning
from macblock.constants import (
    APP_LABEL,
    DNSMASQ_LISTEN_ADDR,
    DNSMASQ_LISTEN_PORT,
    LAUNCHD_DIR,
    LAUNCHD_DNSMASQ_PLIST,
    SYSTEM_BLOCKLIST_FILE,
    SYSTEM_DNSMASQ_CONF,
    SYSTEM_DNS_EXCLUDE_SERVICES_FILE,
    SYSTEM_RAW_BLOCKLIST_FILE,
    SYSTEM_STATE_FILE,
    SYSTEM_VERSION_FILE,
    VAR_DB_DAEMON_PID,
    VAR_DB_DAEMON_READY,
    VAR_DB_DNSMASQ_PID,
    VAR_DB_UPSTREAM_CONF,
)
from macblock.exec import run
from macblock.state import load_state
from macblock.system_dns import get_dns_servers


def _check_file(path) -> tuple[bool, str]:
    ok = path.exists()
    return ok, str(path)


def _tcp_connect_ok(host: str, port: int) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return False

    try:
        s.settimeout(0.3)
        s.connect((host, port))
        return True
    except OSError as e:
        if e.errno in {errno.ECONNREFUSED, errno.ETIMEDOUT, errno.EHOSTUNREACH, errno.ENETUNREACH}:
            return False
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def _check_version() -> tuple[bool, str | None]:
    if not SYSTEM_VERSION_FILE.exists():
        return False, None

    try:
        installed = SYSTEM_VERSION_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return False, None

    if installed != __version__:
        return False, installed

    return True, installed


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


def _check_port_in_use(host: str, port: int) -> str | None:
    r = run(["/usr/sbin/lsof", "-i", f":{port}", "-P", "-n"])
    if r.returncode == 0 and r.stdout.strip():
        lines = r.stdout.strip().split("\n")
        if len(lines) > 1:
            parts = lines[1].split()
            if parts:
                return parts[0]
    return None


def run_diagnostics() -> int:
    print(bold("macblock doctor"))
    print()

    daemon_plist = LAUNCHD_DIR / f"{APP_LABEL}.daemon.plist"
    issues: list[str] = []
    suggestions: list[str] = []

    print(bold("Configuration Files"))
    checks = [
        ("state.json", SYSTEM_STATE_FILE),
        ("version", SYSTEM_VERSION_FILE),
        ("dnsmasq.conf", SYSTEM_DNSMASQ_CONF),
        ("blocklist.raw", SYSTEM_RAW_BLOCKLIST_FILE),
        ("blocklist.conf", SYSTEM_BLOCKLIST_FILE),
        ("upstream.conf", VAR_DB_UPSTREAM_CONF),
        ("dns.exclude_services", SYSTEM_DNS_EXCLUDE_SERVICES_FILE),
    ]

    for name, path in checks:
        ok, p = _check_file(path)
        status = success("OK") if ok else error("MISSING")
        print(f"  {name}: {status} ({p})")
        if not ok:
            issues.append(f"{name} is missing")

    print()
    print(bold("Launchd Services"))
    plist_checks = [
        ("dnsmasq", LAUNCHD_DNSMASQ_PLIST),
        ("daemon", daemon_plist),
    ]

    for name, plist in plist_checks:
        ok, p = _check_file(plist)
        status = success("OK") if ok else error("MISSING")
        print(f"  {APP_LABEL}.{name}: {status}")
        if not ok:
            issues.append(f"launchd plist for {name} is missing")

    version_ok, installed_version = _check_version()
    print()
    print(bold("Version"))
    if not version_ok:
        if installed_version is None:
            print(f"  installed: {error('unknown')}")
            print(f"  cli: {__version__}")
            issues.append("version file missing")
            suggestions.append("sudo macblock install --force")
        else:
            print(f"  installed: {warning(installed_version)}")
            print(f"  cli: {__version__}")
            issues.append(f"version mismatch (installed={installed_version}, cli={__version__})")
            suggestions.append("sudo macblock install --force")
    else:
        print(f"  version: {success(__version__)}")

    print()
    print(bold("Blocklist"))
    if SYSTEM_BLOCKLIST_FILE.exists():
        try:
            size = SYSTEM_BLOCKLIST_FILE.stat().st_size
            line_count = len(SYSTEM_BLOCKLIST_FILE.read_text().splitlines())
        except Exception:
            size = 0
            line_count = 0

        if size == 0 or line_count == 0:
            print(f"  entries: {error('0 (empty)')}")
            issues.append("blocklist is empty")
            suggestions.append("sudo macblock update")
        else:
            print(f"  entries: {success(str(line_count))}")
    else:
        print(f"  blocklist: {error('not found')}")
        issues.append("blocklist file not found")
        suggestions.append("sudo macblock update")

    print()
    print(bold("Upstream DNS"))
    if VAR_DB_UPSTREAM_CONF.exists():
        try:
            upstream_text = VAR_DB_UPSTREAM_CONF.read_text(encoding="utf-8")
            server_count = upstream_text.count("server=")
        except Exception:
            upstream_text = ""
            server_count = 0

        if server_count == 0:
            print(f"  servers: {error('0 (none configured)')}")
            issues.append("no upstream DNS servers configured")
            suggestions.append("sudo launchctl kickstart -k system/com.local.macblock.daemon")
        else:
            print(f"  servers: {success(str(server_count))}")
    else:
        print(f"  upstream.conf: {error('not found')}")

    print()
    print(bold("dnsmasq Process"))
    dnsmasq_pid = _read_pid_file(VAR_DB_DNSMASQ_PID)

    if dnsmasq_pid is None:
        print(f"  pid file: {warning('missing')}")
        issues.append("dnsmasq PID file missing")
    elif not _is_process_running(dnsmasq_pid):
        print(f"  pid: {error(f'{dnsmasq_pid} (not running)')}")
        issues.append(f"dnsmasq process {dnsmasq_pid} not running")
        suggestions.append("sudo launchctl kickstart -k system/com.local.macblock.dnsmasq")
    else:
        print(f"  pid: {success(str(dnsmasq_pid))}")
        r_cmd = run(["/bin/ps", "-p", str(dnsmasq_pid), "-o", "command="])
        cmd = r_cmd.stdout.strip() if r_cmd.returncode == 0 else ""
        if cmd and str(SYSTEM_DNSMASQ_CONF) not in cmd:
            print(f"  {warning('process may not be macblock-managed')}")

    port_ok = _tcp_connect_ok(DNSMASQ_LISTEN_ADDR, DNSMASQ_LISTEN_PORT)
    if port_ok:
        print(f"  listening: {success(f'{DNSMASQ_LISTEN_ADDR}:{DNSMASQ_LISTEN_PORT}')}")
    else:
        print(f"  listening: {error(f'not on {DNSMASQ_LISTEN_ADDR}:{DNSMASQ_LISTEN_PORT}')}")
        issues.append(f"dnsmasq not listening on port {DNSMASQ_LISTEN_PORT}")

        blocker = _check_port_in_use(DNSMASQ_LISTEN_ADDR, DNSMASQ_LISTEN_PORT)
        if blocker and "dnsmasq" not in blocker.lower():
            print(f"  {warning(f'port in use by: {blocker}')}")
            issues.append(f"port {DNSMASQ_LISTEN_PORT} in use by {blocker}")

    print()
    print(bold("macblock Daemon"))
    daemon_pid = _read_pid_file(VAR_DB_DAEMON_PID)

    if daemon_pid is None:
        print(f"  pid file: {warning('missing')}")
        issues.append("daemon PID file missing")
    elif not _is_process_running(daemon_pid):
        print(f"  pid: {error(f'{daemon_pid} (not running)')}")
        issues.append(f"daemon process {daemon_pid} not running")
        suggestions.append("sudo launchctl kickstart -k system/com.local.macblock.daemon")
    else:
        print(f"  pid: {success(str(daemon_pid))}")

    if VAR_DB_DAEMON_READY.exists():
        print(f"  ready: {success('yes')}")
    else:
        print(f"  ready: {warning('no (not yet signaled)')}")
        if daemon_pid and _is_process_running(daemon_pid):
            issues.append("daemon running but not ready")

    print()
    print(bold("DNS State"))
    st = load_state(SYSTEM_STATE_FILE)

    enabled_str = success("enabled") if st.enabled else info("disabled")
    print(f"  blocking: {enabled_str}")

    now = int(time.time())
    paused = st.resume_at_epoch is not None and st.resume_at_epoch > now
    if paused and st.resume_at_epoch is not None:
        remaining = st.resume_at_epoch - now
        mins = remaining // 60
        print(f"  paused: {warning(f'yes (resumes in {mins}m)')}")

    if st.managed_services:
        print(f"  managed services: {len(st.managed_services)}")
        dns_issues = []
        for svc in st.managed_services:
            cur = get_dns_servers(svc)
            expected_localhost = st.enabled and not paused
            if expected_localhost and cur != ["127.0.0.1"]:
                dns_issues.append(f"{svc}: expected 127.0.0.1, got {cur}")
            elif not expected_localhost and cur == ["127.0.0.1"]:
                dns_issues.append(f"{svc}: still pointing to localhost")

        if dns_issues:
            for issue in dns_issues:
                print(f"    {warning(issue)}")
                issues.append(f"DNS misconfigured: {issue}")
    else:
        print(f"  managed services: {warning('none')}")

    r_dns = run(["/usr/sbin/scutil", "--dns"])
    if r_dns.returncode == 0:
        dns_output = (r_dns.stdout or "").lower()
        if "encrypted" in dns_output or "doh" in dns_output or "dot" in dns_output:
            print()
            print(warning("Encrypted DNS (DoH/DoT) detected - may bypass macblock"))
            issues.append("encrypted DNS may bypass blocking")

    print()
    print(bold("Summary"))
    print(f"  label: {APP_LABEL}")

    if not issues:
        print(f"  status: {success('all checks passed')}")
        return 0

    print(f"  status: {error(f'{len(issues)} issue(s) found')}")
    print()
    print(bold("Issues"))
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {error(issue)}")

    if suggestions:
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique_suggestions.append(s)

        print()
        print(bold("Suggested Fixes"))
        for s in unique_suggestions:
            print(f"  {info(s)}")

    return 1
