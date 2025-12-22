from __future__ import annotations

import os
import pwd
from pathlib import Path

from macblock.colors import print_info, print_success, print_warning
from macblock.constants import (
    APP_LABEL,
    DNSMASQ_USER,
    LAUNCHD_DIR,
    LAUNCHD_DAEMON_PLIST,
    LAUNCHD_DNSMASQ_PLIST,
    LAUNCHD_STATE_PLIST,
    LAUNCHD_UPSTREAMS_PLIST,
    SYSTEM_BIN_DIR,
    SYSTEM_BLACKLIST_FILE,
    SYSTEM_BLOCKLIST_FILE,
    SYSTEM_CONFIG_DIR,
    SYSTEM_DNSMASQ_CONF,
    SYSTEM_DNS_EXCLUDE_SERVICES_FILE,
    SYSTEM_RAW_BLOCKLIST_FILE,
    SYSTEM_RESOLVER_DIR,
    SYSTEM_STATE_FILE,
    SYSTEM_SUPPORT_DIR,
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
from macblock.templates import read_template
from macblock.users import delete_system_user, ensure_system_user


def _render_template(name: str, mapping: dict[str, str]) -> str:
    text = read_template(name)
    for k, v in mapping.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def _chown(path: Path, user: str) -> None:
    pw = pwd.getpwnam(user)
    os.chown(path, pw.pw_uid, pw.pw_gid)


def _find_dnsmasq_bin() -> str:
    candidates = [
        os.environ.get("MACBLOCK_DNSMASQ_BIN", ""),
        "/opt/homebrew/opt/dnsmasq/sbin/dnsmasq",
        "/usr/local/opt/dnsmasq/sbin/dnsmasq",
        "/opt/homebrew/sbin/dnsmasq",
        "/usr/local/sbin/dnsmasq",
    ]
    for c in candidates:
        if not c:
            continue
        if Path(c).exists():
            return c
    raise MacblockError("dnsmasq not found; install with 'brew install dnsmasq'")


def _require_system_python3() -> None:
    python3 = Path("/usr/bin/python3")
    if not python3.exists():
        raise MacblockError(
            "System /usr/bin/python3 is required (try: xcode-select --install). "
            "macblock installs root launchd jobs that run via /usr/bin/python3."
        )


def _write_helpers() -> None:
    ensure_dir(SYSTEM_BIN_DIR, mode=0o755)

    mapping = {
        "APP_LABEL": APP_LABEL,
        "SYSTEM_STATE_FILE": str(SYSTEM_STATE_FILE),
        "UPSTREAM_OUT": str(VAR_DB_UPSTREAM_CONF),
        "DNSMASQ_PID_FILE": str(VAR_DB_DNSMASQ_PID),
        "DAEMON_PID_FILE": str(VAR_DB_DAEMON_PID),
        "DNS_EXCLUDE_SERVICES_FILE": str(SYSTEM_DNS_EXCLUDE_SERVICES_FILE),
        "RESOLVER_DIR": str(SYSTEM_RESOLVER_DIR),
    }

    helpers: list[tuple[str, Path, int]] = [
        ("macblockd.py.tmpl", SYSTEM_BIN_DIR / "macblockd.py", 0o755),
    ]

    for src, dst, mode in helpers:
        atomic_write_text(dst, _render_template(src, mapping), mode=mode)
        os.chown(dst, 0, 0)


def _write_launchd_plists(dnsmasq_bin: str) -> None:
    dnsmasq_plist = _render_template(
        "launchd-dnsmasq.plist",
        {
            "APP_LABEL": APP_LABEL,
            "DNSMASQ_BIN": dnsmasq_bin,
            "DNSMASQ_CONF": str(SYSTEM_DNSMASQ_CONF),
            "DNSMASQ_USER": DNSMASQ_USER,
            "DNSMASQ_STDOUT": str(SYSTEM_LOG_DIR / "dnsmasq.out.log"),
            "DNSMASQ_STDERR": str(SYSTEM_LOG_DIR / "dnsmasq.err.log"),
        },
    )


    daemon_plist = _render_template(
        "launchd-macblockd.plist",
        {
            "APP_LABEL": APP_LABEL,
            "MACBLOCKD_BIN": str(SYSTEM_BIN_DIR / "macblockd.py"),
            "MACBLOCKD_STDOUT": str(SYSTEM_LOG_DIR / "daemon.out.log"),
            "MACBLOCKD_STDERR": str(SYSTEM_LOG_DIR / "daemon.err.log"),
        },
    )

    for path, content in [
        (LAUNCHD_DNSMASQ_PLIST, dnsmasq_plist),
        (LAUNCHD_DAEMON_PLIST, daemon_plist),
    ]:
        atomic_write_text(path, content, mode=0o644)
        os.chown(path, 0, 0)


def _bootstrap(plist: Path, label: str) -> None:
    bootstrap_system(plist)
    enable_service(label)
    kickstart(label)


def _detect_existing_install() -> list[str]:
    leftovers: list[str] = []

    old_pf_plist = LAUNCHD_DIR / f"{APP_LABEL}.pf.plist"

    for p in [
        SYSTEM_SUPPORT_DIR,
        SYSTEM_DNSMASQ_CONF,
        SYSTEM_STATE_FILE,
        LAUNCHD_DNSMASQ_PLIST,
        LAUNCHD_DAEMON_PLIST,
        LAUNCHD_UPSTREAMS_PLIST,
        LAUNCHD_STATE_PLIST,
        old_pf_plist,
    ]:
        if p.exists():
            leftovers.append(str(p))

    return leftovers


def do_install(force: bool = False) -> int:
    existing = _detect_existing_install()
    if existing:
        msg = "existing macblock installation detected: " + ", ".join(existing)
        if force:
            print_warning(msg)
        else:
            raise MacblockError(msg + ". Run: sudo macblock uninstall (or pass --force).")

    _require_system_python3()
    dnsmasq_bin = _find_dnsmasq_bin()

    ensure_system_user(DNSMASQ_USER)

    ensure_dir(SYSTEM_SUPPORT_DIR, mode=0o755)
    ensure_dir(SYSTEM_CONFIG_DIR, mode=0o755)
    ensure_dir(SYSTEM_BIN_DIR, mode=0o755)
    ensure_dir(SYSTEM_LOG_DIR, mode=0o755)
    ensure_dir(VAR_DB_DIR, mode=0o755)
    ensure_dir(VAR_DB_DNSMASQ_DIR, mode=0o755)

    os.chown(SYSTEM_SUPPORT_DIR, 0, 0)
    os.chown(SYSTEM_CONFIG_DIR, 0, 0)
    os.chown(SYSTEM_BIN_DIR, 0, 0)
    os.chown(SYSTEM_LOG_DIR, 0, 0)
    os.chown(VAR_DB_DIR, 0, 0)

    _chown(VAR_DB_DNSMASQ_DIR, DNSMASQ_USER)

    if not SYSTEM_WHITELIST_FILE.exists():
        atomic_write_text(SYSTEM_WHITELIST_FILE, "", mode=0o644)
        os.chown(SYSTEM_WHITELIST_FILE, 0, 0)

    if not SYSTEM_BLACKLIST_FILE.exists():
        atomic_write_text(SYSTEM_BLACKLIST_FILE, "", mode=0o644)
        os.chown(SYSTEM_BLACKLIST_FILE, 0, 0)

    if not SYSTEM_BLOCKLIST_FILE.exists():
        atomic_write_text(SYSTEM_BLOCKLIST_FILE, "", mode=0o644)
        os.chown(SYSTEM_BLOCKLIST_FILE, 0, 0)

    if not SYSTEM_RAW_BLOCKLIST_FILE.exists():
        atomic_write_text(SYSTEM_RAW_BLOCKLIST_FILE, "", mode=0o644)
        os.chown(SYSTEM_RAW_BLOCKLIST_FILE, 0, 0)

    if not VAR_DB_UPSTREAM_CONF.exists():
        atomic_write_text(VAR_DB_UPSTREAM_CONF, "server=1.1.1.1\nserver=8.8.8.8\n", mode=0o644)

    os.chown(VAR_DB_UPSTREAM_CONF, 0, 0)

    atomic_write_text(SYSTEM_DNSMASQ_CONF, render_dnsmasq_conf(), mode=0o644)
    os.chown(SYSTEM_DNSMASQ_CONF, 0, 0)

    if not SYSTEM_DNS_EXCLUDE_SERVICES_FILE.exists():
        atomic_write_text(
            SYSTEM_DNS_EXCLUDE_SERVICES_FILE,
            "# One network service name per line (exact match)\n",
            mode=0o644,
        )
        os.chown(SYSTEM_DNS_EXCLUDE_SERVICES_FILE, 0, 0)

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
        os.chown(SYSTEM_STATE_FILE, 0, 0)

    _write_helpers()
    _write_launchd_plists(dnsmasq_bin)

    old_pf_plist = LAUNCHD_DIR / f"{APP_LABEL}.pf.plist"

    if force:
        for label in [f"{APP_LABEL}.state", f"{APP_LABEL}.upstreams"]:
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

    print_info("installing launchd jobs")

    _bootstrap(LAUNCHD_DNSMASQ_PLIST, f"{APP_LABEL}.dnsmasq")
    _bootstrap(LAUNCHD_DAEMON_PLIST, f"{APP_LABEL}.daemon")

    print_warning("macblock is not enabled by install; run: sudo macblock enable")
    print_success("installed")
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
        SYSTEM_BIN_DIR / "apply-state.py",
        SYSTEM_BIN_DIR / "update-upstreams.py",
        SYSTEM_BIN_DIR / "macblockd.py",
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

    for d in [SYSTEM_BIN_DIR, SYSTEM_CONFIG_DIR, SYSTEM_LOG_DIR, SYSTEM_SUPPORT_DIR]:
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
