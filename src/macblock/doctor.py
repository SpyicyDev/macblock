from __future__ import annotations

import os
import socket
import sys
import time
from macblock import __version__
from macblock.constants import (
    APP_LABEL,
    DNSMASQ_LISTEN_ADDR,
    DNSMASQ_LISTEN_PORT,
    LAUNCHD_DIR,
    LAUNCHD_DNSMASQ_PLIST,
    SYSTEM_BLOCKLIST_FILE,
    SYSTEM_DNSMASQ_CONF,
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
from macblock.ui import (
    cyan,
    dim,
    header,
    list_item,
    list_item_fail,
    list_item_ok,
    list_item_warn,
    red,
    result_success,
    status_err,
    status_info,
    status_ok,
    status_warn,
    subheader,
    SYMBOL_FAIL,
)


def _tcp_connect_ok(host: str, port: int) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return False

    try:
        s.settimeout(0.3)
        s.connect((host, port))
        return True
    except OSError:
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


def _run_diagnostics_plain() -> int:
    header("🔍", "macblock doctor")

    daemon_plist = LAUNCHD_DIR / f"{APP_LABEL}.daemon.plist"
    issues: list[str] = []
    suggestions: list[str] = []

    # Version check
    subheader("Version")
    version_ok, installed_version = _check_version()
    if not version_ok:
        if installed_version is None:
            status_err("Installed", "unknown")
            status_info("CLI", __version__)
            issues.append("version file missing")
            suggestions.append("sudo macblock install --force")
        else:
            status_warn("Installed", installed_version)
            status_info("CLI", __version__)
            issues.append(
                f"version mismatch (installed={installed_version}, cli={__version__})"
            )
            suggestions.append("sudo macblock install --force")
    else:
        status_ok("Version", __version__)

    # Configuration files
    subheader("Configuration Files")
    config_files = [
        ("state.json", SYSTEM_STATE_FILE),
        ("dnsmasq.conf", SYSTEM_DNSMASQ_CONF),
        ("blocklist.raw", SYSTEM_RAW_BLOCKLIST_FILE),
        ("blocklist.conf", SYSTEM_BLOCKLIST_FILE),
        ("upstream.conf", VAR_DB_UPSTREAM_CONF),
    ]

    for name, path in config_files:
        if path.exists():
            list_item_ok(f"{name}")
        else:
            list_item_fail(f"{name} {dim('(missing)')}")
            issues.append(f"{name} is missing")

    # Launchd services
    subheader("Launchd Services")
    plist_checks = [
        ("dnsmasq", LAUNCHD_DNSMASQ_PLIST),
        ("daemon", daemon_plist),
    ]

    for name, plist in plist_checks:
        label = f"{APP_LABEL}.{name}"
        if plist.exists():
            list_item_ok(label)
        else:
            list_item_fail(f"{label} {dim('(not installed)')}")
            issues.append(f"launchd plist for {name} is missing")

    # Blocklist
    subheader("Blocklist")
    if SYSTEM_BLOCKLIST_FILE.exists():
        try:
            size = SYSTEM_BLOCKLIST_FILE.stat().st_size
            line_count = len(SYSTEM_BLOCKLIST_FILE.read_text().splitlines())
        except Exception:
            size = 0
            line_count = 0

        if size == 0 or line_count == 0:
            status_err("Entries", "0 (empty)")
            issues.append("blocklist is empty")
            suggestions.append("sudo macblock update")
        else:
            status_ok("Entries", f"{line_count:,}")
    else:
        status_err("File", "not found")
        issues.append("blocklist file not found")
        suggestions.append("sudo macblock update")

    # Upstream DNS
    subheader("Upstream DNS")
    if VAR_DB_UPSTREAM_CONF.exists():
        try:
            upstream_text = VAR_DB_UPSTREAM_CONF.read_text(encoding="utf-8")
            server_count = upstream_text.count("server=")
        except Exception:
            server_count = 0

        if server_count == 0:
            status_err("Servers", "0 (none configured)")
            issues.append("no upstream DNS servers configured")
            suggestions.append(
                "sudo launchctl kickstart -k system/com.local.macblock.daemon"
            )
        else:
            status_ok("Servers", str(server_count))
    else:
        status_err("Config", "not found")

    # dnsmasq process
    subheader("dnsmasq Process")
    dnsmasq_pid = _read_pid_file(VAR_DB_DNSMASQ_PID)

    if dnsmasq_pid is None:
        status_warn("PID file", "missing")
        issues.append("dnsmasq PID file missing")
    elif not _is_process_running(dnsmasq_pid):
        status_err("PID", f"{dnsmasq_pid} (not running)")
        issues.append(f"dnsmasq process {dnsmasq_pid} not running")
        suggestions.append(
            "sudo launchctl kickstart -k system/com.local.macblock.dnsmasq"
        )
    else:
        status_ok("PID", str(dnsmasq_pid))
        r_cmd = run(["/bin/ps", "-p", str(dnsmasq_pid), "-o", "command="])
        cmd = r_cmd.stdout.strip() if r_cmd.returncode == 0 else ""
        if cmd and str(SYSTEM_DNSMASQ_CONF) not in cmd:
            status_warn("Note", "process may not be macblock-managed")

    port_ok = _tcp_connect_ok(DNSMASQ_LISTEN_ADDR, DNSMASQ_LISTEN_PORT)
    if port_ok:
        status_ok("Listening", f"{DNSMASQ_LISTEN_ADDR}:{DNSMASQ_LISTEN_PORT}")
    else:
        status_err("Listening", f"not on {DNSMASQ_LISTEN_ADDR}:{DNSMASQ_LISTEN_PORT}")
        issues.append(f"dnsmasq not listening on port {DNSMASQ_LISTEN_PORT}")

        blocker = _check_port_in_use(DNSMASQ_LISTEN_ADDR, DNSMASQ_LISTEN_PORT)
        if blocker and "dnsmasq" not in blocker.lower():
            status_warn("Port blocker", blocker)
            issues.append(f"port {DNSMASQ_LISTEN_PORT} in use by {blocker}")

    # Daemon process
    subheader("macblock Daemon")
    daemon_pid = _read_pid_file(VAR_DB_DAEMON_PID)

    if daemon_pid is None:
        status_warn("PID file", "missing")
        issues.append("daemon PID file missing")
    elif not _is_process_running(daemon_pid):
        status_err("PID", f"{daemon_pid} (not running)")
        issues.append(f"daemon process {daemon_pid} not running")
        suggestions.append(
            "sudo launchctl kickstart -k system/com.local.macblock.daemon"
        )
    else:
        status_ok("PID", str(daemon_pid))

    if VAR_DB_DAEMON_READY.exists():
        status_ok("Ready", "yes")
    else:
        status_warn("Ready", "no (not yet signaled)")
        if daemon_pid and _is_process_running(daemon_pid):
            issues.append("daemon running but not ready")

    # DNS state
    subheader("DNS State")
    st = load_state(SYSTEM_STATE_FILE)

    now = int(time.time())
    paused = st.resume_at_epoch is not None and st.resume_at_epoch > now

    if st.enabled and not paused:
        status_ok("Blocking", "enabled")
    elif st.enabled and paused:
        remaining = st.resume_at_epoch - now if st.resume_at_epoch else 0
        mins = remaining // 60
        status_warn("Blocking", f"paused ({mins}m remaining)")
    else:
        status_info("Blocking", "disabled")

    if st.managed_services:
        status_info("Managed", f"{len(st.managed_services)} services")
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
                list_item_warn(issue)
                issues.append(f"DNS misconfigured: {issue}")
    else:
        status_warn("Managed", "no services")

    # Check for encrypted DNS
    r_dns = run(["/usr/sbin/scutil", "--dns"])
    if r_dns.returncode == 0:
        dns_output = (r_dns.stdout or "").lower()
        if "encrypted" in dns_output or "doh" in dns_output or "dot" in dns_output:
            print()
            list_item_warn("Encrypted DNS (DoH/DoT) detected - may bypass macblock")
            issues.append("encrypted DNS may bypass blocking")

    # Summary
    print()
    if not issues:
        result_success("All checks passed")
        return 0

    print(f"\n{red(SYMBOL_FAIL)} {len(issues)} issue(s) found")

    if issues:
        print()
        subheader("Issues")
        for issue in issues:
            list_item_fail(issue)

    if suggestions:
        seen: set[str] = set()
        unique_suggestions: list[str] = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique_suggestions.append(s)

        print()
        subheader("Suggested Fixes")
        for s in unique_suggestions:
            list_item(cyan(s))

    print()
    return 1


def _run_diagnostics_rich() -> int:
    import importlib

    box = importlib.import_module("rich.box")
    Console = importlib.import_module("rich.console").Console
    Padding = importlib.import_module("rich.padding").Padding
    Rule = importlib.import_module("rich.rule").Rule
    Table = importlib.import_module("rich.table").Table
    Text = importlib.import_module("rich.text").Text

    content_width = min(88, Console().width)
    console = Console(width=content_width)

    def pad(renderable: object) -> object:
        return Padding(renderable, (0, 0, 0, 1))

    def badge(level: str) -> object:
        if level == "ok":
            return Text("OK", style="green")
        if level == "warn":
            return Text("WARN", style="yellow")
        if level == "info":
            return Text("INFO", style="cyan")
        return Text("FAIL", style="red")

    console.print(pad(Text("macblock doctor", style="bold")))

    daemon_plist = LAUNCHD_DIR / f"{APP_LABEL}.daemon.plist"
    issues: list[str] = []
    suggestions: list[str] = []

    console.print(pad(Rule("Version", style="dim")))
    version_ok, installed_version = _check_version()

    version = Table.grid(padding=(0, 1))
    version.add_column(style="bold", no_wrap=True)
    version.add_column()

    if not version_ok:
        if installed_version is None:
            version.add_row("Installed", "unknown")
            version.add_row("CLI", __version__)
            issues.append("version file missing")
            suggestions.append("sudo macblock install --force")
        else:
            version.add_row("Installed", installed_version)
            version.add_row("CLI", __version__)
            issues.append(
                f"version mismatch (installed={installed_version}, cli={__version__})"
            )
            suggestions.append("sudo macblock install --force")
    else:
        version.add_row("Version", f"[green]{__version__}[/green]")

    console.print(pad(version))

    console.print(pad(Rule("Configuration Files", style="dim")))
    config = Table(
        box=box.MINIMAL, show_edge=False, pad_edge=False, header_style="bold"
    )
    config.add_column("File", no_wrap=True)
    config.add_column("Status", no_wrap=True)

    config_files = [
        ("state.json", SYSTEM_STATE_FILE),
        ("dnsmasq.conf", SYSTEM_DNSMASQ_CONF),
        ("blocklist.raw", SYSTEM_RAW_BLOCKLIST_FILE),
        ("blocklist.conf", SYSTEM_BLOCKLIST_FILE),
        ("upstream.conf", VAR_DB_UPSTREAM_CONF),
    ]

    for name, path in config_files:
        if path.exists():
            config.add_row(name, badge("ok"))
        else:
            config.add_row(name, badge("fail"))
            issues.append(f"{name} is missing")

    console.print(pad(config))

    console.print(pad(Rule("Launchd", style="dim")))
    launchd = Table(
        box=box.MINIMAL, show_edge=False, pad_edge=False, header_style="bold"
    )
    launchd.add_column("Service", no_wrap=True)
    launchd.add_column("Status", no_wrap=True)

    plist_checks = [
        (f"{APP_LABEL}.dnsmasq", LAUNCHD_DNSMASQ_PLIST),
        (f"{APP_LABEL}.daemon", daemon_plist),
    ]

    for label, plist in plist_checks:
        if plist.exists():
            launchd.add_row(label, badge("ok"))
        else:
            launchd.add_row(label, badge("fail"))
            issues.append(f"launchd plist missing: {label}")

    console.print(pad(launchd))

    console.print(pad(Rule("Blocklist", style="dim")))
    blocklist = Table.grid(padding=(0, 1))
    blocklist.add_column(style="bold", no_wrap=True)
    blocklist.add_column()

    if SYSTEM_BLOCKLIST_FILE.exists():
        try:
            size = SYSTEM_BLOCKLIST_FILE.stat().st_size
            line_count = len(SYSTEM_BLOCKLIST_FILE.read_text().splitlines())
        except Exception:
            size = 0
            line_count = 0

        if size == 0 or line_count == 0:
            blocklist.add_row("Entries", "[red]0[/red] [dim](empty)[/dim]")
            issues.append("blocklist is empty")
            suggestions.append("sudo macblock update")
        else:
            blocklist.add_row("Entries", f"[green]{line_count:,}[/green]")
    else:
        blocklist.add_row("File", "[red]not found[/red]")
        issues.append("blocklist file not found")
        suggestions.append("sudo macblock update")

    console.print(pad(blocklist))

    console.print(pad(Rule("Upstream DNS", style="dim")))
    upstream = Table.grid(padding=(0, 1))
    upstream.add_column(style="bold", no_wrap=True)
    upstream.add_column()

    if VAR_DB_UPSTREAM_CONF.exists():
        try:
            upstream_text = VAR_DB_UPSTREAM_CONF.read_text(encoding="utf-8")
            server_count = upstream_text.count("server=")
        except Exception:
            server_count = 0

        if server_count == 0:
            upstream.add_row("Servers", "[red]0[/red] [dim](none configured)[/dim]")
            issues.append("no upstream DNS servers configured")
            suggestions.append(
                "sudo launchctl kickstart -k system/com.local.macblock.daemon"
            )
        else:
            upstream.add_row("Servers", f"[green]{server_count}[/green]")
    else:
        upstream.add_row("Config", "[red]not found[/red]")

    console.print(pad(upstream))

    console.print(pad(Rule("dnsmasq", style="dim")))
    dnsmasq = Table.grid(padding=(0, 1))
    dnsmasq.add_column(style="bold", no_wrap=True)
    dnsmasq.add_column()

    dnsmasq_pid = _read_pid_file(VAR_DB_DNSMASQ_PID)
    if dnsmasq_pid is None:
        dnsmasq.add_row("PID", "[yellow]missing[/yellow]")
        issues.append("dnsmasq PID file missing")
    elif not _is_process_running(dnsmasq_pid):
        dnsmasq.add_row("PID", f"[red]{dnsmasq_pid}[/red] [dim](not running)[/dim]")
        issues.append(f"dnsmasq process {dnsmasq_pid} not running")
        suggestions.append(
            "sudo launchctl kickstart -k system/com.local.macblock.dnsmasq"
        )
    else:
        dnsmasq.add_row("PID", f"[green]{dnsmasq_pid}[/green]")

    port_ok = _tcp_connect_ok(DNSMASQ_LISTEN_ADDR, DNSMASQ_LISTEN_PORT)
    if port_ok:
        dnsmasq.add_row(
            "Listening", f"[green]{DNSMASQ_LISTEN_ADDR}:{DNSMASQ_LISTEN_PORT}[/green]"
        )
    else:
        dnsmasq.add_row(
            "Listening",
            f"[red]not on {DNSMASQ_LISTEN_ADDR}:{DNSMASQ_LISTEN_PORT}[/red]",
        )
        issues.append(f"dnsmasq not listening on port {DNSMASQ_LISTEN_PORT}")

        blocker = _check_port_in_use(DNSMASQ_LISTEN_ADDR, DNSMASQ_LISTEN_PORT)
        if blocker and "dnsmasq" not in blocker.lower():
            dnsmasq.add_row("Port blocker", f"[yellow]{blocker}[/yellow]")
            issues.append(f"port {DNSMASQ_LISTEN_PORT} in use by {blocker}")

    console.print(pad(dnsmasq))

    console.print(pad(Rule("Daemon", style="dim")))
    daemon = Table.grid(padding=(0, 1))
    daemon.add_column(style="bold", no_wrap=True)
    daemon.add_column()

    daemon_pid = _read_pid_file(VAR_DB_DAEMON_PID)
    if daemon_pid is None:
        daemon.add_row("PID", "[yellow]missing[/yellow]")
        issues.append("daemon PID file missing")
    elif not _is_process_running(daemon_pid):
        daemon.add_row("PID", f"[red]{daemon_pid}[/red] [dim](not running)[/dim]")
        issues.append(f"daemon process {daemon_pid} not running")
        suggestions.append(
            "sudo launchctl kickstart -k system/com.local.macblock.daemon"
        )
    else:
        daemon.add_row("PID", f"[green]{daemon_pid}[/green]")

    daemon.add_row(
        "Ready",
        "[green]yes[/green]" if VAR_DB_DAEMON_READY.exists() else "[yellow]no[/yellow]",
    )
    if (
        daemon_pid
        and _is_process_running(daemon_pid)
        and not VAR_DB_DAEMON_READY.exists()
    ):
        issues.append("daemon running but not ready")

    console.print(pad(daemon))

    console.print(pad(Rule("DNS State", style="dim")))
    st = load_state(SYSTEM_STATE_FILE)

    now = int(time.time())
    paused = st.resume_at_epoch is not None and st.resume_at_epoch > now

    dns_state = Table.grid(padding=(0, 1))
    dns_state.add_column(style="bold", no_wrap=True)
    dns_state.add_column()

    if st.enabled and not paused:
        dns_state.add_row("Blocking", "[green]enabled[/green]")
    elif st.enabled and paused:
        remaining = st.resume_at_epoch - now if st.resume_at_epoch else 0
        mins = remaining // 60
        dns_state.add_row(
            "Blocking", f"[yellow]paused[/yellow] [dim]({mins}m remaining)[/dim]"
        )
    else:
        dns_state.add_row("Blocking", "[dim]disabled[/dim]")

    if st.managed_services:
        dns_state.add_row("Managed", f"{len(st.managed_services)} services")
        dns_issues: list[str] = []
        for svc in st.managed_services:
            cur = get_dns_servers(svc)
            expected_localhost = st.enabled and not paused
            if expected_localhost and cur != ["127.0.0.1"]:
                dns_issues.append(f"{svc}: expected 127.0.0.1, got {cur}")
            elif not expected_localhost and cur == ["127.0.0.1"]:
                dns_issues.append(f"{svc}: still pointing to localhost")

        for issue in dns_issues:
            issues.append(f"DNS misconfigured: {issue}")

    else:
        dns_state.add_row("Managed", "[yellow]none[/yellow]")

    r_dns = run(["/usr/sbin/scutil", "--dns"])
    if r_dns.returncode == 0:
        dns_output = (r_dns.stdout or "").lower()
        if "encrypted" in dns_output or "doh" in dns_output or "dot" in dns_output:
            dns_state.add_row("Encrypted", "[yellow]DoH/DoT detected[/yellow]")
            issues.append("encrypted DNS may bypass blocking")

    console.print(pad(dns_state))

    if not issues:
        console.print(pad(Text("All checks passed", style="green")))
        return 0

    console.print(pad(Rule(f"{len(issues)} issue(s)", style="red")))
    issues_table = Table(box=None, show_header=False, pad_edge=False)
    issues_table.add_column()
    for issue in issues:
        issues_table.add_row(Text(f"✗ {issue}", style="red"))
    console.print(pad(issues_table))

    if suggestions:
        seen: set[str] = set()
        unique_suggestions: list[str] = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique_suggestions.append(s)

        console.print(pad(Rule("Suggested Fixes", style="dim")))
        sugg_table = Table(box=None, show_header=False, pad_edge=False)
        sugg_table.add_column()
        for s in unique_suggestions:
            sugg_table.add_row(Text(s, style="cyan"))
        console.print(pad(sugg_table))

    return 1


def run_diagnostics() -> int:
    if sys.stdout.isatty():
        return _run_diagnostics_rich()
    return _run_diagnostics_plain()
