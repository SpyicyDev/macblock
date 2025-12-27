from __future__ import annotations

import time
from datetime import datetime

from macblock.constants import (
    APP_LABEL,
    LAUNCHD_DIR,
    LAUNCHD_DNSMASQ_PLIST,
    SYSTEM_BLOCKLIST_FILE,
    SYSTEM_STATE_FILE,
    VAR_DB_DAEMON_PID,
    VAR_DB_DAEMON_LAST_APPLY,
    VAR_DB_DNSMASQ_PID,
)
from macblock.exec import run
from macblock.state import load_state
from macblock.system_dns import get_dns_servers
from macblock.ui import (
    dns_status,
    header,
    status_active,
    status_err,
    status_inactive,
    status_info,
    status_ok,
    status_warn,
    subheader,
)


def _read_pid(path) -> int | None:
    if not path.exists():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
        return pid if pid > 1 else None
    except Exception:
        return None


def _process_running(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        import os

        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _get_blocklist_count() -> int:
    if not SYSTEM_BLOCKLIST_FILE.exists():
        return 0
    try:
        return len(SYSTEM_BLOCKLIST_FILE.read_text().splitlines())
    except Exception:
        return 0


def show_status() -> int:
    st = load_state(SYSTEM_STATE_FILE)

    header("📊", "macblock status")

    # Blocking status
    now = int(time.time())
    paused = st.resume_at_epoch is not None and st.resume_at_epoch > now

    if st.enabled and not paused:
        status_active("Blocking", "enabled")
    elif st.enabled and paused:
        remaining = st.resume_at_epoch - now if st.resume_at_epoch else 0
        mins = remaining // 60
        status_warn("Blocking", f"paused ({mins}m remaining)")
    else:
        status_inactive("Blocking", "disabled")

    # Resume timer
    if st.resume_at_epoch is not None:
        when = datetime.fromtimestamp(st.resume_at_epoch)
        status_info("Resume at", when.strftime("%H:%M:%S"))

    # dnsmasq process
    subheader("Services")

    dnsmasq_pid = _read_pid(VAR_DB_DNSMASQ_PID)
    if dnsmasq_pid and _process_running(dnsmasq_pid):
        status_ok("dnsmasq", f"running (PID {dnsmasq_pid})")
    else:
        r = run(["/usr/bin/pgrep", "-x", "dnsmasq"])
        if r.returncode == 0:
            status_warn("dnsmasq", "running (not managed by macblock)")
        else:
            status_err("dnsmasq", "not running")

    # Daemon process
    daemon_pid = _read_pid(VAR_DB_DAEMON_PID)
    if daemon_pid and _process_running(daemon_pid):
        status_ok("daemon", f"running (PID {daemon_pid})")
    else:
        status_err("daemon", "not running")

    if VAR_DB_DAEMON_LAST_APPLY.exists():
        try:
            last_apply = int(
                VAR_DB_DAEMON_LAST_APPLY.read_text(encoding="utf-8").strip()
            )
            age_s = max(0, int(time.time()) - last_apply)
            status_info("Last apply", f"{age_s}s ago")
        except Exception:
            status_warn("Last apply", "unknown")
    else:
        status_warn("Last apply", "unknown")

    # Blocklist
    subheader("Blocklist")

    count = _get_blocklist_count()
    if count > 0:
        status_ok("Domains", f"{count:,} blocked")
    else:
        status_err("Domains", "0 (run: sudo macblock update)")

    source = st.blocklist_source or "stevenblack"
    status_info("Source", source)

    # DNS Configuration
    if st.managed_services:
        subheader("DNS Configuration")

        is_blocking = st.enabled and not paused
        for svc in st.managed_services:
            servers = get_dns_servers(svc)
            dns_status(svc, servers, is_active=True, is_blocking=is_blocking)

    # Installation status
    subheader("Installation")

    daemon_plist = LAUNCHD_DIR / f"{APP_LABEL}.daemon.plist"
    dnsmasq_plist_exists = LAUNCHD_DNSMASQ_PLIST.exists()
    daemon_plist_exists = daemon_plist.exists()

    if dnsmasq_plist_exists and daemon_plist_exists:
        status_ok("Launchd", "installed")
    elif dnsmasq_plist_exists or daemon_plist_exists:
        status_warn("Launchd", "partially installed")
    else:
        status_err("Launchd", "not installed")

    status_info("Label", APP_LABEL)

    print()
    return 0
