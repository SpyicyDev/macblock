from __future__ import annotations

from datetime import datetime

from macblock.colors import bold, dim, error, info, success
from macblock.constants import (
    APP_LABEL,
    LAUNCHD_DIR,
    LAUNCHD_DNSMASQ_PLIST,
    SYSTEM_DNSMASQ_CONF,
    SYSTEM_DNS_EXCLUDE_SERVICES_FILE,
    SYSTEM_STATE_FILE,
    VAR_DB_DNSMASQ_PID,
    VAR_DB_UPSTREAM_CONF,
)
from macblock.exec import run
from macblock.state import load_state
from macblock.system_dns import get_dns_servers


def _exists(path_str: str, ok: bool) -> str:
    return success(path_str) if ok else error(path_str)


def show_status() -> int:
    st = load_state(SYSTEM_STATE_FILE)

    print(bold("macblock status"))

    print(f"label: {APP_LABEL}")
    print(f"enabled: {success('true') if st.enabled else dim('false')}")
    print(f"dnsmasq_conf: {_exists(str(SYSTEM_DNSMASQ_CONF), SYSTEM_DNSMASQ_CONF.exists())}")
    print(f"dnsmasq_pid: {_exists(str(VAR_DB_DNSMASQ_PID), VAR_DB_DNSMASQ_PID.exists())}")
    print(f"upstream_conf: {_exists(str(VAR_DB_UPSTREAM_CONF), VAR_DB_UPSTREAM_CONF.exists())}")
    print(f"dns_exclude_services: {_exists(str(SYSTEM_DNS_EXCLUDE_SERVICES_FILE), SYSTEM_DNS_EXCLUDE_SERVICES_FILE.exists())}")

    daemon_plist = LAUNCHD_DIR / f"{APP_LABEL}.daemon.plist"

    plists = [
        (f"{APP_LABEL}.dnsmasq", LAUNCHD_DNSMASQ_PLIST),
        (f"{APP_LABEL}.daemon", daemon_plist),
    ]

    for label, plist in plists:
        print(f"launchd[{label}]: {_exists(str(plist), plist.exists())}")

    if st.resume_at_epoch is None:
        print("resume_at: " + dim(""))
    else:
        when = datetime.fromtimestamp(st.resume_at_epoch)
        print(f"resume_at: {when.isoformat(sep=' ', timespec='seconds')}")

    if st.managed_services:
        print()
        print(info("managed services"))
        for svc in st.managed_services:
            cur = get_dns_servers(svc)
            if cur is None:
                cur_s = dim("dhcp")
            else:
                cur_s = ", ".join(cur)
            print(f"{svc}: {cur_s}")

    r = run(["/usr/bin/pgrep", "-x", "dnsmasq"])
    if r.returncode == 0:
        print()
        if VAR_DB_DNSMASQ_PID.exists():
            print("dnsmasq: " + success("running"))
        else:
            print("dnsmasq: " + error("running but macblock pid-file missing"))
    else:
        print()
        print("dnsmasq: " + error("not running or not visible"))

    return 0
