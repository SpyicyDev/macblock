from __future__ import annotations

import sys
import time
from datetime import datetime

from macblock.constants import (
    APP_LABEL,
    LAUNCHD_DIR,
    LAUNCHD_DNSMASQ_PLIST,
    SYSTEM_BLOCKLIST_FILE,
    SYSTEM_STATE_FILE,
    VAR_DB_DAEMON_PID,
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


def _show_status_plain() -> int:
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


def _show_status_rich() -> int:
    import importlib

    box = importlib.import_module("rich.box")
    Console = importlib.import_module("rich.console").Console
    Padding = importlib.import_module("rich.padding").Padding
    Rule = importlib.import_module("rich.rule").Rule
    Table = importlib.import_module("rich.table").Table
    Text = importlib.import_module("rich.text").Text

    st = load_state(SYSTEM_STATE_FILE)

    now = int(time.time())
    paused = st.resume_at_epoch is not None and st.resume_at_epoch > now

    content_width = min(88, Console().width)
    console = Console(width=content_width)

    def pad(renderable: object) -> object:
        return Padding(renderable, (0, 0, 0, 1))

    def badge(level: str) -> object:
        if level == "ok":
            return Text("OK", style="green")
        if level == "warn":
            return Text("WARN", style="yellow")
        return Text("FAIL", style="red")

    console.print(pad(Text("macblock status", style="bold")))

    summary = Table.grid(padding=(0, 1))
    summary.add_column(style="bold", no_wrap=True)
    summary.add_column()

    if st.enabled and not paused:
        blocking_value = "[green]enabled[/green]"
    elif st.enabled and paused:
        remaining = st.resume_at_epoch - now if st.resume_at_epoch else 0
        mins = remaining // 60
        blocking_value = f"[yellow]paused[/yellow] [dim]({mins}m remaining)[/dim]"
    else:
        blocking_value = "[dim]disabled[/dim]"

    summary.add_row("Blocking", blocking_value)

    if st.resume_at_epoch is not None:
        when = datetime.fromtimestamp(st.resume_at_epoch)
        summary.add_row("Resume at", when.strftime("%H:%M:%S"))

    console.print(pad(summary))

    console.print(pad(Rule("Services", style="dim")))

    services = Table(
        box=box.MINIMAL,
        show_edge=False,
        pad_edge=False,
        header_style="bold",
        show_header=True,
    )
    services.add_column("Service", no_wrap=True)
    services.add_column("Status", no_wrap=True)
    services.add_column("Detail")

    dnsmasq_pid = _read_pid(VAR_DB_DNSMASQ_PID)
    if dnsmasq_pid and _process_running(dnsmasq_pid):
        services.add_row("dnsmasq", badge("ok"), f"running (PID {dnsmasq_pid})")
    else:
        r = run(["/usr/bin/pgrep", "-x", "dnsmasq"])
        if r.returncode == 0:
            services.add_row("dnsmasq", badge("warn"), "running (not managed)")
        else:
            services.add_row("dnsmasq", badge("fail"), "not running")

    daemon_pid = _read_pid(VAR_DB_DAEMON_PID)
    if daemon_pid and _process_running(daemon_pid):
        services.add_row("daemon", badge("ok"), f"running (PID {daemon_pid})")
    else:
        services.add_row("daemon", badge("fail"), "not running")

    console.print(pad(services))

    console.print(pad(Rule("Blocklist", style="dim")))

    count = _get_blocklist_count()
    source = st.blocklist_source or "stevenblack"

    blocklist = Table.grid(padding=(0, 1))
    blocklist.add_column(style="bold", no_wrap=True)
    blocklist.add_column()

    if count > 0:
        blocklist.add_row("Domains", f"[green]{count:,}[/green] blocked")
    else:
        blocklist.add_row(
            "Domains", "[red]0[/red] [dim](run: sudo macblock update)[/dim]"
        )

    blocklist.add_row("Source", source)
    console.print(pad(blocklist))

    if st.managed_services:
        console.print(pad(Rule("DNS", style="dim")))

        dns_table = Table(
            box=box.MINIMAL,
            show_edge=False,
            pad_edge=False,
            header_style="bold",
            show_header=True,
        )
        dns_table.add_column("Service", no_wrap=True)
        dns_table.add_column("Servers")

        is_blocking = st.enabled and not paused
        for svc in st.managed_services:
            servers = get_dns_servers(svc)
            if servers is None or len(servers) == 0:
                dns_str = "[dim]DHCP[/dim]"
            elif servers == ["127.0.0.1"]:
                suffix = " [dim](blocking)[/dim]" if is_blocking else ""
                dns_str = f"[green]→[/green] 127.0.0.1{suffix}"
            else:
                dns_str = ", ".join(servers)
            dns_table.add_row(svc, dns_str)

        console.print(pad(dns_table))

    console.print(pad(Rule("Installation", style="dim")))

    daemon_plist = LAUNCHD_DIR / f"{APP_LABEL}.daemon.plist"
    dnsmasq_plist_exists = LAUNCHD_DNSMASQ_PLIST.exists()
    daemon_plist_exists = daemon_plist.exists()

    if dnsmasq_plist_exists and daemon_plist_exists:
        launchd_value = "[green]installed[/green]"
    elif dnsmasq_plist_exists or daemon_plist_exists:
        launchd_value = "[yellow]partial[/yellow]"
    else:
        launchd_value = "[red]not installed[/red]"

    install = Table.grid(padding=(0, 1))
    install.add_column(style="bold", no_wrap=True)
    install.add_column()
    install.add_row("Launchd", launchd_value)
    install.add_row("Label", APP_LABEL)

    console.print(pad(install))

    return 0


def show_status() -> int:
    if sys.stdout.isatty():
        return _show_status_rich()
    return _show_status_plain()
