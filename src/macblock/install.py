from __future__ import annotations

import errno
import os
import pwd
import shutil
import socket
import sys
import time
from pathlib import Path

from macblock import __version__
from macblock.colors import print_error, print_info, print_success, print_warning
from macblock.constants import (
    APP_LABEL,
    DNSMASQ_LISTEN_ADDR,
    DNSMASQ_LISTEN_PORT,
    DNSMASQ_USER,
    LAUNCHD_DIR,
    LAUNCHD_DAEMON_PLIST,
    LAUNCHD_DNSMASQ_PLIST,
    LAUNCHD_STATE_PLIST,
    LAUNCHD_UPSTREAMS_PLIST,
    SYSTEM_BLACKLIST_FILE,
    SYSTEM_BLOCKLIST_FILE,
    SYSTEM_CONFIG_DIR,
    SYSTEM_DNSMASQ_CONF,
    SYSTEM_DNS_EXCLUDE_SERVICES_FILE,
    SYSTEM_RAW_BLOCKLIST_FILE,
    SYSTEM_RESOLVER_DIR,
    SYSTEM_STATE_FILE,
    SYSTEM_SUPPORT_DIR,
    SYSTEM_VERSION_FILE,
    SYSTEM_WHITELIST_FILE,
    SYSTEM_LOG_DIR,
    VAR_DB_DAEMON_PID,
    VAR_DB_DNSMASQ_DIR,
    VAR_DB_DNSMASQ_PID,
    VAR_DB_DIR,
    VAR_DB_UPSTREAM_CONF,
)
from macblock.dnsmasq import render_dnsmasq_conf
from macblock.errors import MacblockError
from macblock.exec import run
from macblock.fs import atomic_write_text, ensure_dir
from macblock.launchd import bootout_label, bootout_system, bootstrap_system, enable_service, kickstart, service_exists
from macblock.state import State, load_state, save_state_atomic
from macblock.system_dns import ServiceDnsBackup, restore_from_backup
from macblock.users import delete_system_user, ensure_system_user


def _chown_root(path: Path) -> None:
    os.chown(path, 0, 0)


def _chown_user(path: Path, user: str) -> None:
    pw = pwd.getpwnam(user)
    os.chown(path, pw.pw_uid, pw.pw_gid)


def _check_port_available(host: str, port: int) -> tuple[bool, str | None]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.bind((host, port))
        s.close()
        return True, None
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            r = run(["/usr/sbin/lsof", "-i", f":{port}", "-P", "-n"])
            if r.returncode == 0 and r.stdout.strip():
                lines = r.stdout.strip().split("\n")
                if len(lines) > 1:
                    parts = lines[1].split()
                    if parts:
                        return False, parts[0]
            return False, "unknown process"
        return False, str(e)
    except Exception as e:
        return False, str(e)


def _check_dnsmasq_installed() -> tuple[bool, str | None]:
    candidates = [
        os.environ.get("MACBLOCK_DNSMASQ_BIN", ""),
        "/opt/homebrew/opt/dnsmasq/sbin/dnsmasq",
        "/usr/local/opt/dnsmasq/sbin/dnsmasq",
        "/opt/homebrew/sbin/dnsmasq",
        "/usr/local/sbin/dnsmasq",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return True, c
    return False, None


def _find_dnsmasq_bin() -> str:
    found, path = _check_dnsmasq_installed()
    if found and path:
        return path
    raise MacblockError("dnsmasq not found; install with 'brew install dnsmasq'")


def _find_macblock_bin() -> str:
    candidates = [
        os.environ.get("MACBLOCK_BIN", ""),
        "/opt/homebrew/bin/macblock",
        "/usr/local/bin/macblock",
        shutil.which("macblock"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c

    exe = sys.executable
    if exe:
        venv_bin = Path(exe).parent / "macblock"
        if venv_bin.exists():
            return str(venv_bin)

    raise MacblockError("macblock binary not found in PATH")


def _render_dnsmasq_plist(dnsmasq_bin: str) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{APP_LABEL}.dnsmasq</string>
  <key>ProgramArguments</key>
  <array>
    <string>{dnsmasq_bin}</string>
    <string>--keep-in-foreground</string>
    <string>-C</string>
    <string>{SYSTEM_DNSMASQ_CONF}</string>
  </array>
  <key>StandardOutPath</key>
  <string>{SYSTEM_LOG_DIR}/dnsmasq.out.log</string>
  <key>StandardErrorPath</key>
  <string>{SYSTEM_LOG_DIR}/dnsmasq.err.log</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
'''


def _render_daemon_plist(macblock_bin: str) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{APP_LABEL}.daemon</string>
  <key>ProgramArguments</key>
  <array>
    <string>{macblock_bin}</string>
    <string>daemon</string>
  </array>
  <key>StandardOutPath</key>
  <string>{SYSTEM_LOG_DIR}/daemon.out.log</string>
  <key>StandardErrorPath</key>
  <string>{SYSTEM_LOG_DIR}/daemon.err.log</string>
  <key>WorkingDirectory</key>
  <string>/var/empty</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
'''


def _bootstrap(plist: Path, label: str) -> None:
    bootstrap_system(plist)
    enable_service(label)
    kickstart(label)


def _detect_existing_install() -> list[str]:
    leftovers: list[str] = []

    old_pf_plist = LAUNCHD_DIR / f"{APP_LABEL}.pf.plist"
    old_bin_dir = SYSTEM_SUPPORT_DIR / "bin"

    for p in [
        SYSTEM_SUPPORT_DIR,
        SYSTEM_DNSMASQ_CONF,
        SYSTEM_STATE_FILE,
        LAUNCHD_DNSMASQ_PLIST,
        LAUNCHD_DAEMON_PLIST,
        LAUNCHD_UPSTREAMS_PLIST,
        LAUNCHD_STATE_PLIST,
        old_pf_plist,
        old_bin_dir,
    ]:
        if p.exists():
            leftovers.append(str(p))

    return leftovers


def _cleanup_old_install() -> None:
    old_pf_plist = LAUNCHD_DIR / f"{APP_LABEL}.pf.plist"
    old_bin_dir = SYSTEM_SUPPORT_DIR / "bin"

    for label in [f"{APP_LABEL}.state", f"{APP_LABEL}.upstreams", f"{APP_LABEL}.pf"]:
        try:
            bootout_label(label)
        except Exception:
            pass

    for plist in [old_pf_plist, LAUNCHD_STATE_PLIST, LAUNCHD_UPSTREAMS_PLIST, LAUNCHD_DNSMASQ_PLIST, LAUNCHD_DAEMON_PLIST]:
        if plist.exists():
            try:
                bootout_system(plist)
            except Exception:
                pass

    for p in [
        old_bin_dir / "apply-state.py",
        old_bin_dir / "update-upstreams.py",
        old_bin_dir / "macblockd.py",
    ]:
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    if old_bin_dir.exists():
        try:
            old_bin_dir.rmdir()
        except Exception:
            pass


def _run_preflight_checks(force: bool) -> tuple[str, str]:
    print_info("running pre-flight checks...")

    dnsmasq_installed, dnsmasq_bin = _check_dnsmasq_installed()
    if not dnsmasq_installed or dnsmasq_bin is None:
        raise MacblockError(
            "dnsmasq is not installed.\n"
            "  Install with: brew install dnsmasq\n"
            "  Then re-run: sudo macblock install"
        )

    port_available, blocker = _check_port_available(DNSMASQ_LISTEN_ADDR, DNSMASQ_LISTEN_PORT)
    if not port_available:
        if blocker and "dnsmasq" in blocker.lower():
            if not force:
                raise MacblockError(
                    f"Port {DNSMASQ_LISTEN_PORT} is in use by {blocker}.\n"
                    "  This may be from a previous installation.\n"
                    "  Run: sudo macblock install --force"
                )
        else:
            raise MacblockError(
                f"Port {DNSMASQ_LISTEN_PORT} is already in use by: {blocker}\n"
                "  macblock needs this port for DNS.\n"
                "  Stop the conflicting service and retry."
            )

    macblock_bin = _find_macblock_bin()

    return dnsmasq_bin, macblock_bin


def _wait_for_dnsmasq_ready(timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect((DNSMASQ_LISTEN_ADDR, DNSMASQ_LISTEN_PORT))
            s.close()
            return True
        except OSError:
            pass
        time.sleep(0.2)
    return False


def _wait_for_daemon_ready(timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if VAR_DB_DAEMON_PID.exists():
            try:
                pid = int(VAR_DB_DAEMON_PID.read_text(encoding="utf-8").strip())
                if pid > 1:
                    r = run(["/bin/ps", "-p", str(pid)])
                    if r.returncode == 0:
                        return True
            except Exception:
                pass
        time.sleep(0.2)
    return False


def _verify_services_running() -> tuple[bool, list[str]]:
    issues: list[str] = []

    if not _wait_for_dnsmasq_ready(timeout=5.0):
        issues.append(f"dnsmasq not listening on {DNSMASQ_LISTEN_ADDR}:{DNSMASQ_LISTEN_PORT}")
        if SYSTEM_LOG_DIR.exists():
            err_log = SYSTEM_LOG_DIR / "dnsmasq.err.log"
            if err_log.exists():
                try:
                    content = err_log.read_text(encoding="utf-8").strip()
                    if content:
                        last_lines = "\n".join(content.split("\n")[-5:])
                        issues.append(f"dnsmasq error log:\n{last_lines}")
                except Exception:
                    pass

    if not _wait_for_daemon_ready(timeout=5.0):
        issues.append("daemon not running (PID file missing or process not found)")
        if SYSTEM_LOG_DIR.exists():
            err_log = SYSTEM_LOG_DIR / "daemon.err.log"
            if err_log.exists():
                try:
                    content = err_log.read_text(encoding="utf-8").strip()
                    if content:
                        last_lines = "\n".join(content.split("\n")[-5:])
                        issues.append(f"daemon error log:\n{last_lines}")
                except Exception:
                    pass

    return len(issues) == 0, issues


def do_install(force: bool = False, skip_update: bool = False) -> int:
    existing = _detect_existing_install()
    if existing:
        msg = "existing macblock installation detected"
        if force:
            print_warning(msg + " - upgrading")
            _cleanup_old_install()
        else:
            raise MacblockError(msg + "; run: sudo macblock uninstall (or pass --force)")

    dnsmasq_bin, macblock_bin = _run_preflight_checks(force)

    print_info(f"using dnsmasq: {dnsmasq_bin}")
    print_info(f"using macblock: {macblock_bin}")

    print_info("creating system user...")
    ensure_system_user(DNSMASQ_USER)

    print_info("creating directories...")
    ensure_dir(SYSTEM_SUPPORT_DIR, mode=0o755)
    ensure_dir(SYSTEM_CONFIG_DIR, mode=0o755)
    ensure_dir(SYSTEM_LOG_DIR, mode=0o755)
    ensure_dir(VAR_DB_DIR, mode=0o755)
    ensure_dir(VAR_DB_DNSMASQ_DIR, mode=0o755)

    _chown_root(SYSTEM_SUPPORT_DIR)
    _chown_root(SYSTEM_CONFIG_DIR)
    _chown_root(SYSTEM_LOG_DIR)
    _chown_root(VAR_DB_DIR)
    _chown_user(VAR_DB_DNSMASQ_DIR, DNSMASQ_USER)

    print_info("writing configuration files...")

    if not SYSTEM_WHITELIST_FILE.exists():
        atomic_write_text(SYSTEM_WHITELIST_FILE, "", mode=0o644)
        _chown_root(SYSTEM_WHITELIST_FILE)

    if not SYSTEM_BLACKLIST_FILE.exists():
        atomic_write_text(SYSTEM_BLACKLIST_FILE, "", mode=0o644)
        _chown_root(SYSTEM_BLACKLIST_FILE)

    if not SYSTEM_BLOCKLIST_FILE.exists():
        atomic_write_text(SYSTEM_BLOCKLIST_FILE, "", mode=0o644)
        _chown_root(SYSTEM_BLOCKLIST_FILE)

    if not SYSTEM_RAW_BLOCKLIST_FILE.exists():
        atomic_write_text(SYSTEM_RAW_BLOCKLIST_FILE, "", mode=0o644)
        _chown_root(SYSTEM_RAW_BLOCKLIST_FILE)

    if not VAR_DB_UPSTREAM_CONF.exists():
        atomic_write_text(VAR_DB_UPSTREAM_CONF, "server=1.1.1.1\nserver=8.8.8.8\n", mode=0o644)
    _chown_root(VAR_DB_UPSTREAM_CONF)

    atomic_write_text(SYSTEM_DNSMASQ_CONF, render_dnsmasq_conf(), mode=0o644)
    _chown_root(SYSTEM_DNSMASQ_CONF)

    if not SYSTEM_DNS_EXCLUDE_SERVICES_FILE.exists():
        atomic_write_text(
            SYSTEM_DNS_EXCLUDE_SERVICES_FILE,
            "# One network service name per line (exact match)\n",
            mode=0o644,
        )
        _chown_root(SYSTEM_DNS_EXCLUDE_SERVICES_FILE)

    if not SYSTEM_STATE_FILE.exists():
        save_state_atomic(
            SYSTEM_STATE_FILE,
            State(
                schema_version=2,
                enabled=False,
                resume_at_epoch=None,
                blocklist_source=None,
                dns_backup={},
                managed_services=[],
                resolver_domains=[],
            ),
        )
        _chown_root(SYSTEM_STATE_FILE)

    atomic_write_text(SYSTEM_VERSION_FILE, f"{__version__}\n", mode=0o644)
    _chown_root(SYSTEM_VERSION_FILE)

    dnsmasq_plist = _render_dnsmasq_plist(dnsmasq_bin)
    daemon_plist = _render_daemon_plist(macblock_bin)

    atomic_write_text(LAUNCHD_DNSMASQ_PLIST, dnsmasq_plist, mode=0o644)
    _chown_root(LAUNCHD_DNSMASQ_PLIST)

    atomic_write_text(LAUNCHD_DAEMON_PLIST, daemon_plist, mode=0o644)
    _chown_root(LAUNCHD_DAEMON_PLIST)

    print_info("starting launchd services...")

    _bootstrap(LAUNCHD_DNSMASQ_PLIST, f"{APP_LABEL}.dnsmasq")
    _bootstrap(LAUNCHD_DAEMON_PLIST, f"{APP_LABEL}.daemon")

    print_info("verifying services...")
    services_ok, issues = _verify_services_running()

    if not services_ok:
        print_error("service verification failed:")
        for issue in issues:
            print_error(f"  {issue}")
        print_warning("installation may be incomplete; run 'macblock doctor' for diagnostics")
        return 1

    print_success(f"installed macblock {__version__}")

    if not skip_update:
        print_info("downloading blocklist (this may take a moment)...")
        try:
            from macblock.blocklists import update_blocklist
            update_blocklist()
        except Exception as e:
            print_warning(f"blocklist download failed: {e}")
            print_warning("run 'sudo macblock update' manually to download blocklist")

    print_success("installation complete!")
    print_info("next steps:")
    print_info("  1. Run 'macblock doctor' to verify installation")
    print_info("  2. Run 'sudo macblock enable' to start blocking")
    return 0


def _remove_any_macblock_resolvers() -> None:
    if not SYSTEM_RESOLVER_DIR.exists():
        return

    for p in SYSTEM_RESOLVER_DIR.iterdir():
        try:
            if not p.is_file():
                continue
        except Exception:
            continue

        try:
            head = p.read_text(encoding="utf-8", errors="ignore")[:64]
        except Exception:
            continue

        if not head.startswith("# macblock"):
            continue

        try:
            p.unlink()
        except Exception:
            pass


def _restore_dns_from_state(st: State) -> None:
    for service in st.managed_services:
        cfg = st.dns_backup.get(service)
        if not isinstance(cfg, dict):
            continue
        dns_val = cfg.get("dns")
        search_val = cfg.get("search")
        backup = ServiceDnsBackup(
            dns_servers=list(dns_val) if isinstance(dns_val, list) else None,
            search_domains=list(search_val) if isinstance(search_val, list) else None,
        )
        restore_from_backup(service, backup)


def do_uninstall(force: bool = False) -> int:
    st = load_state(SYSTEM_STATE_FILE)

    try:
        _restore_dns_from_state(st)
    except Exception:
        if not force:
            raise

    try:
        _remove_any_macblock_resolvers()
    except Exception:
        if not force:
            raise

    old_pf_plist = LAUNCHD_DIR / f"{APP_LABEL}.pf.plist"
    old_bin_dir = SYSTEM_SUPPORT_DIR / "bin"

    for plist in [old_pf_plist, LAUNCHD_STATE_PLIST, LAUNCHD_UPSTREAMS_PLIST, LAUNCHD_DNSMASQ_PLIST, LAUNCHD_DAEMON_PLIST]:
        try:
            if plist.exists():
                bootout_system(plist)
        except Exception:
            if not force:
                raise

    for p in [LAUNCHD_DNSMASQ_PLIST, LAUNCHD_DAEMON_PLIST, LAUNCHD_UPSTREAMS_PLIST, LAUNCHD_STATE_PLIST, old_pf_plist]:
        if p.exists():
            p.unlink()

    for p in [
        old_bin_dir / "apply-state.py",
        old_bin_dir / "update-upstreams.py",
        old_bin_dir / "macblockd.py",
    ]:
        if p.exists():
            p.unlink()

    for p in [
        VAR_DB_DNSMASQ_PID,
        VAR_DB_DNSMASQ_DIR / "dnsmasq.log",
        VAR_DB_UPSTREAM_CONF,
        VAR_DB_DAEMON_PID,
    ]:
        if p.exists():
            p.unlink()

    for d in [VAR_DB_DNSMASQ_DIR, VAR_DB_DIR]:
        if d.exists():
            try:
                d.rmdir()
            except Exception:
                pass

    for p in [
        SYSTEM_DNSMASQ_CONF,
        SYSTEM_RAW_BLOCKLIST_FILE,
        SYSTEM_BLOCKLIST_FILE,
        SYSTEM_WHITELIST_FILE,
        SYSTEM_BLACKLIST_FILE,
        SYSTEM_STATE_FILE,
        SYSTEM_VERSION_FILE,
        SYSTEM_DNS_EXCLUDE_SERVICES_FILE,
        SYSTEM_LOG_DIR / "dnsmasq.out.log",
        SYSTEM_LOG_DIR / "dnsmasq.err.log",
        SYSTEM_LOG_DIR / "daemon.out.log",
        SYSTEM_LOG_DIR / "daemon.err.log",
        SYSTEM_LOG_DIR / "upstreams.out.log",
        SYSTEM_LOG_DIR / "upstreams.err.log",
        SYSTEM_LOG_DIR / "state.out.log",
        SYSTEM_LOG_DIR / "state.err.log",
    ]:
        if p.exists():
            p.unlink()

    for d in [old_bin_dir, SYSTEM_CONFIG_DIR, SYSTEM_LOG_DIR, SYSTEM_SUPPORT_DIR]:
        if d.exists():
            try:
                d.rmdir()
            except Exception:
                pass

    if force:
        try:
            delete_system_user(DNSMASQ_USER)
        except Exception:
            pass

    leftovers: list[str] = []

    for label in [
        f"{APP_LABEL}.dnsmasq",
        f"{APP_LABEL}.daemon",
        f"{APP_LABEL}.upstreams",
        f"{APP_LABEL}.state",
        f"{APP_LABEL}.pf",
    ]:
        if service_exists(label):
            leftovers.append(f"launchd {label}")

    if leftovers:
        msg = "uninstall incomplete: " + ", ".join(leftovers)
        if force:
            print_warning(msg)
        else:
            raise MacblockError(msg)

    print_success("uninstalled")
    return 0
