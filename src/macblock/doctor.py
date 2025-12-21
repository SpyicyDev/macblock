from __future__ import annotations

import errno
import socket

from macblock.colors import bold, error, info, success, warning
from macblock.constants import (
    APP_LABEL,
    DNSMASQ_LISTEN_ADDR,
    DNSMASQ_LISTEN_ADDR_V6,
    DNSMASQ_LISTEN_PORT,
    LAUNCHD_DNSMASQ_PLIST,
    LAUNCHD_PF_PLIST,
    LAUNCHD_UPSTREAMS_PLIST,
    PF_ANCHOR_FILE,
    PF_CONF,
    PF_EXCLUDE_INTERFACES_FILE,
    SYSTEM_BLOCKLIST_FILE,
    SYSTEM_DNSMASQ_CONF,
    SYSTEM_RAW_BLOCKLIST_FILE,
    SYSTEM_STATE_FILE,
    VAR_DB_DNSMASQ_PID,
    VAR_DB_UPSTREAM_CONF,
)
from macblock.exec import run
from macblock.platform import is_root
from macblock.pf import validate_pf_conf


def _check_file(path) -> tuple[bool, str]:
    ok = path.exists()
    return ok, str(path)


def _tcp_connect_ok(host: str, port: int, *, family: int) -> bool:
    try:
        s = socket.socket(family, socket.SOCK_STREAM)
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


def run_diagnostics() -> int:
    print(bold("macblock doctor"))

    checks = [
        ("state", SYSTEM_STATE_FILE),
        ("pf.conf", PF_CONF),
        ("pf anchor", PF_ANCHOR_FILE),
        ("dnsmasq.conf", SYSTEM_DNSMASQ_CONF),
        ("blocklist.raw", SYSTEM_RAW_BLOCKLIST_FILE),
        ("blocklist.conf", SYSTEM_BLOCKLIST_FILE),
        ("upstream.conf", VAR_DB_UPSTREAM_CONF),
        ("plist dnsmasq", LAUNCHD_DNSMASQ_PLIST),
        ("plist upstreams", LAUNCHD_UPSTREAMS_PLIST),
        ("plist pf", LAUNCHD_PF_PLIST),
    ]

    ok_all = True

    for name, path in checks:
        ok, p = _check_file(path)
        ok_all = ok_all and ok
        print(f"{name}: " + (success(p) if ok else error(p)))

    if SYSTEM_BLOCKLIST_FILE.exists():
        try:
            size = SYSTEM_BLOCKLIST_FILE.stat().st_size
        except Exception:
            size = 0

        if size == 0:
            print(warning("blocklist.conf is empty; run 'sudo macblock update'"))

    pid_ok = False
    pid = None
    if VAR_DB_DNSMASQ_PID.exists():
        try:
            pid = int(VAR_DB_DNSMASQ_PID.read_text(encoding="utf-8").strip())
        except Exception:
            pid = None

    if pid is not None and pid > 1:
        r_ps = run(["/bin/ps", "-p", str(pid)])
        pid_ok = r_ps.returncode == 0

    if pid is None:
        print(warning(f"dnsmasq pid-file missing: {VAR_DB_DNSMASQ_PID}"))
    elif not pid_ok:
        ok_all = False
        print(error(f"dnsmasq pid not running: {pid}"))
    else:
        print(info("dnsmasq pid: ") + success(str(pid)))
        r_cmd = run(["/bin/ps", "-p", str(pid), "-o", "command="])
        cmd = r_cmd.stdout.strip() if r_cmd.returncode == 0 else ""
        if cmd and str(SYSTEM_DNSMASQ_CONF) not in cmd:
            print(warning("dnsmasq process does not appear to be macblock-managed"))

    ok_v4_tcp = _tcp_connect_ok(DNSMASQ_LISTEN_ADDR, DNSMASQ_LISTEN_PORT, family=socket.AF_INET)
    ok_v6_tcp = _tcp_connect_ok(DNSMASQ_LISTEN_ADDR_V6, DNSMASQ_LISTEN_PORT, family=socket.AF_INET6)

    if pid_ok and not (ok_v4_tcp or ok_v6_tcp):
        ok_all = False
        print(error(f"dnsmasq not listening on {DNSMASQ_LISTEN_ADDR}:{DNSMASQ_LISTEN_PORT} or {DNSMASQ_LISTEN_ADDR_V6}:{DNSMASQ_LISTEN_PORT}"))

    r_if = run(["/sbin/ifconfig", "-l"])
    ifaces = r_if.stdout.strip().split() if r_if.returncode == 0 else []
    vpn_ifaces = [x for x in ifaces if x.startswith("utun") or x.startswith("ppp")]
    if vpn_ifaces:
        excluded = []
        if PF_EXCLUDE_INTERFACES_FILE.exists():
            excluded = [
                line.strip()
                for line in PF_EXCLUDE_INTERFACES_FILE.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        missing = [x for x in vpn_ifaces if x not in excluded]
        if missing:
            print(
                warning(
                    "VPN interfaces detected (" + ", ".join(missing) + "). "
                    "If your VPN breaks, add them to "
                    + str(PF_EXCLUDE_INTERFACES_FILE)
                    + " and re-enable macblock."
                )
            )

    if is_root() and PF_CONF.exists():
        try:
            validate_pf_conf()
            print(info("pf.conf syntax: ") + success("ok"))
        except Exception as e:
            ok_all = False
            print(info("pf.conf syntax: ") + error(str(e)))
    else:
        print(warning("Run 'sudo macblock doctor' to validate PF config"))

    r = run(["/usr/bin/pgrep", "-x", "dnsmasq"])
    if r.returncode == 0:
        if pid is None:
            print(info("dnsmasq: ") + warning("some dnsmasq is running (pid-file missing)"))
        else:
            print(info("dnsmasq: ") + success("running"))
    else:
        print(info("dnsmasq: ") + warning("not running or not visible"))

    print(info("label: ") + APP_LABEL)

    return 0 if ok_all else 1
