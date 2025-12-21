from __future__ import annotations

import os
import pwd
from pathlib import Path

from macblock.colors import info, success, warning
from macblock.constants import (
    APP_LABEL,
    DNSMASQ_USER,
    LAUNCHD_DNSMASQ_PLIST,
    LAUNCHD_PF_PLIST,
    LAUNCHD_UPSTREAMS_PLIST,
    PF_ANCHOR_FILE,
    PF_CONF,
    PF_EXCLUDE_INTERFACES_FILE,
    PF_LOCK_FILE,
    SYSTEM_BIN_DIR,
    SYSTEM_BLACKLIST_FILE,
    SYSTEM_BLOCKLIST_FILE,
    SYSTEM_CONFIG_DIR,
    SYSTEM_DNSMASQ_CONF,
    SYSTEM_RAW_BLOCKLIST_FILE,
    SYSTEM_STATE_FILE,
    SYSTEM_SUPPORT_DIR,
    SYSTEM_WHITELIST_FILE,
    VAR_DB_DNSMASQ_PID,
    VAR_DB_DIR,
    VAR_DB_UPSTREAM_CONF,
)
from macblock.dnsmasq import render_dnsmasq_conf
from macblock.errors import MacblockError
from macblock.exec import run
from macblock.fs import atomic_write_text, ensure_dir
from macblock.launchd import bootout_system, bootstrap_system, enable_service, kickstart, service_exists
from macblock.pf import disable_anchor, ensure_pf_conf_block, remove_pf_conf_block, validate_pf_conf, write_anchor_file
from macblock.state import State, save_state_atomic
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
        "PF_ANCHOR_FILE": str(PF_ANCHOR_FILE),
        "PF_LOCK_FILE": str(SYSTEM_SUPPORT_DIR / "pf.lock"),
        "SYSTEM_STATE_FILE": str(SYSTEM_STATE_FILE),
        "UPSTREAM_OUT": str(VAR_DB_UPSTREAM_CONF),
        "DNSMASQ_PID_FILE": str(VAR_DB_DNSMASQ_PID),
    }

    helpers: list[tuple[str, Path, int]] = [
        ("apply_state.py.tmpl", SYSTEM_BIN_DIR / "apply-state.py", 0o755),
        ("update_upstreams.py.tmpl", SYSTEM_BIN_DIR / "update-upstreams.py", 0o755),
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
            "DNSMASQ_STDOUT": str(VAR_DB_DIR / "dnsmasq.out.log"),
            "DNSMASQ_STDERR": str(VAR_DB_DIR / "dnsmasq.err.log"),
        },
    )

    upstreams_plist = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
        "<plist version=\"1.0\">\n"
        "<dict>\n"
        "  <key>Label</key>\n"
        f"  <string>{APP_LABEL}.upstreams</string>\n"
        "  <key>ProgramArguments</key>\n"
        "  <array>\n"
        "    <string>/usr/bin/python3</string>\n"
        f"    <string>{SYSTEM_BIN_DIR / 'update-upstreams.py'}</string>\n"
        "  </array>\n"
        "  <key>StartInterval</key>\n"
        "  <integer>30</integer>\n"
        "  <key>UserName</key>\n"
        f"  <string>{DNSMASQ_USER}</string>\n"
        "  <key>GroupName</key>\n"
        f"  <string>{DNSMASQ_USER}</string>\n"
        "  <key>StandardOutPath</key>\n"
        f"  <string>{VAR_DB_DIR / 'upstreams.out.log'}</string>\n"
        "  <key>StandardErrorPath</key>\n"
        f"  <string>{VAR_DB_DIR / 'upstreams.err.log'}</string>\n"
        "  <key>RunAtLoad</key>\n"
        "  <true/>\n"
        "</dict>\n"
        "</plist>\n"
    )

    pf_plist = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
        "<plist version=\"1.0\">\n"
        "<dict>\n"
        "  <key>Label</key>\n"
        f"  <string>{APP_LABEL}.pf</string>\n"
        "  <key>ProgramArguments</key>\n"
        "  <array>\n"
        "    <string>/usr/bin/python3</string>\n"
        f"    <string>{SYSTEM_BIN_DIR / 'apply-state.py'}</string>\n"
        "  </array>\n"
        "  <key>StartInterval</key>\n"
        "  <integer>30</integer>\n"
        "  <key>StandardOutPath</key>\n"
        f"  <string>{VAR_DB_DIR / 'pf.out.log'}</string>\n"
        "  <key>StandardErrorPath</key>\n"
        f"  <string>{VAR_DB_DIR / 'pf.err.log'}</string>\n"
        "  <key>RunAtLoad</key>\n"
        "  <true/>\n"
        "</dict>\n"
        "</plist>\n"
    )

    for path, content in [
        (LAUNCHD_DNSMASQ_PLIST, dnsmasq_plist),
        (LAUNCHD_UPSTREAMS_PLIST, upstreams_plist),
        (LAUNCHD_PF_PLIST, pf_plist),
    ]:
        atomic_write_text(path, content, mode=0o644)
        os.chown(path, 0, 0)


def _bootstrap(plist: Path, label: str) -> None:
    bootstrap_system(plist)
    enable_service(label)
    kickstart(label)


def do_install(force: bool = False) -> int:
    _require_system_python3()
    dnsmasq_bin = _find_dnsmasq_bin()

    ensure_system_user(DNSMASQ_USER)

    ensure_dir(SYSTEM_SUPPORT_DIR, mode=0o755)
    ensure_dir(SYSTEM_CONFIG_DIR, mode=0o755)
    ensure_dir(SYSTEM_BIN_DIR, mode=0o755)
    ensure_dir(VAR_DB_DIR, mode=0o755)

    os.chown(SYSTEM_SUPPORT_DIR, 0, 0)
    os.chown(SYSTEM_CONFIG_DIR, 0, 0)
    os.chown(SYSTEM_BIN_DIR, 0, 0)

    _chown(VAR_DB_DIR, DNSMASQ_USER)

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
        atomic_write_text(VAR_DB_UPSTREAM_CONF, "\n", mode=0o644)
        _chown(VAR_DB_UPSTREAM_CONF, DNSMASQ_USER)

    atomic_write_text(SYSTEM_DNSMASQ_CONF, render_dnsmasq_conf(), mode=0o644)
    os.chown(SYSTEM_DNSMASQ_CONF, 0, 0)

    if not SYSTEM_STATE_FILE.exists():
        save_state_atomic(SYSTEM_STATE_FILE, State(schema_version=1, enabled=False, resume_at_epoch=None, blocklist_source=None))
        os.chown(SYSTEM_STATE_FILE, 0, 0)

    if not PF_EXCLUDE_INTERFACES_FILE.exists():
        atomic_write_text(
            PF_EXCLUDE_INTERFACES_FILE,
            "# One interface name per line (e.g. utun0)\n",
            mode=0o644,
        )
        os.chown(PF_EXCLUDE_INTERFACES_FILE, 0, 0)

    _write_helpers()

    write_anchor_file()
    ensure_pf_conf_block()
    validate_pf_conf()

    _write_launchd_plists(dnsmasq_bin)

    if force:
        for plist in [LAUNCHD_PF_PLIST, LAUNCHD_UPSTREAMS_PLIST, LAUNCHD_DNSMASQ_PLIST]:
            try:
                bootout_system(plist)
            except Exception:
                pass

    info("installing launchd jobs")

    _bootstrap(LAUNCHD_UPSTREAMS_PLIST, f"{APP_LABEL}.upstreams")
    _bootstrap(LAUNCHD_DNSMASQ_PLIST, f"{APP_LABEL}.dnsmasq")
    _bootstrap(LAUNCHD_PF_PLIST, f"{APP_LABEL}.pf")

    warning("PF is not enabled by install; run: sudo macblock enable")
    success("installed")
    return 0


def do_uninstall(force: bool = False) -> int:
    try:
        disable_anchor()
    except Exception:
        if not force:
            raise

    for plist in [LAUNCHD_PF_PLIST, LAUNCHD_UPSTREAMS_PLIST, LAUNCHD_DNSMASQ_PLIST]:
        try:
            bootout_system(plist)
        except Exception:
            if not force:
                raise

    remove_pf_conf_block()

    if PF_ANCHOR_FILE.exists():
        PF_ANCHOR_FILE.unlink()

    for p in [LAUNCHD_DNSMASQ_PLIST, LAUNCHD_UPSTREAMS_PLIST, LAUNCHD_PF_PLIST]:
        if p.exists():
            p.unlink()

    for p in [
        SYSTEM_BIN_DIR / "apply-state.py",
        SYSTEM_BIN_DIR / "update-upstreams.py",
    ]:
        if p.exists():
            p.unlink()

    for p in [VAR_DB_DNSMASQ_PID, VAR_DB_UPSTREAM_CONF]:
        if p.exists():
            p.unlink()

    if VAR_DB_DIR.exists():
        try:
            VAR_DB_DIR.rmdir()
        except Exception:
            pass

    for p in [
        SYSTEM_DNSMASQ_CONF,
        SYSTEM_RAW_BLOCKLIST_FILE,
        SYSTEM_BLOCKLIST_FILE,
        SYSTEM_WHITELIST_FILE,
        SYSTEM_BLACKLIST_FILE,
        SYSTEM_STATE_FILE,
        PF_EXCLUDE_INTERFACES_FILE,
        PF_LOCK_FILE,
    ]:
        if p.exists():
            p.unlink()

    for d in [SYSTEM_BIN_DIR, SYSTEM_CONFIG_DIR, SYSTEM_SUPPORT_DIR]:
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

    for label in [f"{APP_LABEL}.dnsmasq", f"{APP_LABEL}.upstreams", f"{APP_LABEL}.pf"]:
        if service_exists(label):
            leftovers.append(f"launchd {label}")

    if PF_ANCHOR_FILE.exists():
        leftovers.append(f"pf anchor file {PF_ANCHOR_FILE}")

    if PF_CONF.exists():
        text = PF_CONF.read_text(encoding="utf-8")
        if "# macblock begin" in text or "# macblock end" in text:
            leftovers.append(f"pf.conf still contains macblock block ({PF_CONF})")

    r = run(["/sbin/pfctl", "-a", APP_LABEL, "-s", "rules"])
    if r.returncode == 0 and r.stdout.strip():
        leftovers.append("pf anchor rules still loaded")

    if leftovers:
        msg = "uninstall incomplete: " + ", ".join(leftovers)
        if force:
            warning(msg)
        else:
            raise MacblockError(msg)

    success("uninstalled")
    return 0
