from __future__ import annotations

import errno
import socket
import time

from macblock.colors import bold, error, info, success, warning
from macblock.constants import (
    APP_LABEL,
    DNSMASQ_LISTEN_ADDR,
    DNSMASQ_LISTEN_PORT,
    LAUNCHD_DNSMASQ_PLIST,
    LAUNCHD_STATE_PLIST,
    LAUNCHD_UPSTREAMS_PLIST,
    SYSTEM_BLOCKLIST_FILE,
    SYSTEM_DNSMASQ_CONF,
    SYSTEM_DNS_EXCLUDE_SERVICES_FILE,
    SYSTEM_RAW_BLOCKLIST_FILE,
    SYSTEM_STATE_FILE,
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


def run_diagnostics() -> int:
    print(bold("macblock doctor"))

    checks = [
        ("state", SYSTEM_STATE_FILE),
        ("dnsmasq.conf", SYSTEM_DNSMASQ_CONF),
        ("blocklist.raw", SYSTEM_RAW_BLOCKLIST_FILE),
        ("blocklist.conf", SYSTEM_BLOCKLIST_FILE),
        ("upstream.conf", VAR_DB_UPSTREAM_CONF),
        ("dns.exclude_services", SYSTEM_DNS_EXCLUDE_SERVICES_FILE),
        ("plist dnsmasq", LAUNCHD_DNSMASQ_PLIST),
        ("plist upstreams", LAUNCHD_UPSTREAMS_PLIST),
        ("plist state", LAUNCHD_STATE_PLIST),
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

    st = load_state(SYSTEM_STATE_FILE)

    if VAR_DB_UPSTREAM_CONF.exists():
        try:
            upstream_text = VAR_DB_UPSTREAM_CONF.read_text(encoding="utf-8")
        except Exception:
            upstream_text = ""
        if "server=" not in upstream_text:
            ok_all = False
            print(error("upstream.conf has no upstream servers; restart macblock upstreams job"))

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

    if pid_ok and not _tcp_connect_ok(DNSMASQ_LISTEN_ADDR, DNSMASQ_LISTEN_PORT):
        ok_all = False
        print(error(f"dnsmasq not listening on {DNSMASQ_LISTEN_ADDR}:{DNSMASQ_LISTEN_PORT}"))

    now = int(time.time())
    paused = st.resume_at_epoch is not None and st.resume_at_epoch > now

    if st.enabled and not paused and st.managed_services:
        missing = []
        for svc in st.managed_services:
            cur = get_dns_servers(svc)
            if cur != ["127.0.0.1"]:
                missing.append(svc)
        if missing:
            ok_all = False
            print(warning("DNS is not set to localhost for: " + ", ".join(missing)))

    r = run(["/usr/bin/pgrep", "-x", "dnsmasq"])
    if r.returncode == 0:
        if pid is None:
            print(info("dnsmasq: ") + warning("some dnsmasq is running (pid-file missing)"))
        else:
            print(info("dnsmasq: ") + success("running"))
    else:
        print(info("dnsmasq: ") + warning("not running or not visible"))

    r_dns = run(["/usr/sbin/scutil", "--dns"])
    if r_dns.returncode == 0:
        if "encrypted" in (r_dns.stdout or "").lower() or "doh" in (r_dns.stdout or "").lower():
            print(warning("Encrypted DNS may bypass system DNS settings"))

    print(info("label: ") + APP_LABEL)

    return 0 if ok_all else 1
