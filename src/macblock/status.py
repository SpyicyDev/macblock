from __future__ import annotations

from datetime import datetime

from macblock.colors import bold, dim, error, info, success, warning
from macblock.constants import (
    APP_LABEL,
    LAUNCHD_DNSMASQ_PLIST,
    LAUNCHD_PF_PLIST,
    LAUNCHD_UPSTREAMS_PLIST,
    PF_ANCHOR_FILE,
    SYSTEM_DNSMASQ_CONF,
    SYSTEM_STATE_FILE,
)
from macblock.exec import run
from macblock.platform import is_root
from macblock.pf import anchor_rules, pf_info
from macblock.state import load_state


def _exists(path_str: str, ok: bool) -> str:
    return success(path_str) if ok else error(path_str)


def show_status() -> int:
    st = load_state(SYSTEM_STATE_FILE)

    print(bold("macblock status"))

    print(f"label: {APP_LABEL}")
    print(f"pf_anchor: {_exists(str(PF_ANCHOR_FILE), PF_ANCHOR_FILE.exists())}")
    print(f"dnsmasq_conf: {_exists(str(SYSTEM_DNSMASQ_CONF), SYSTEM_DNSMASQ_CONF.exists())}")

    plists = [
        (f"{APP_LABEL}.dnsmasq", LAUNCHD_DNSMASQ_PLIST),
        (f"{APP_LABEL}.upstreams", LAUNCHD_UPSTREAMS_PLIST),
        (f"{APP_LABEL}.pf", LAUNCHD_PF_PLIST),
    ]

    for label, plist in plists:
        print(f"launchd[{label}]: {_exists(str(plist), plist.exists())}")

    if st.resume_at_epoch is None:
        print("resume_at: " + dim(""))
    else:
        when = datetime.fromtimestamp(st.resume_at_epoch)
        print(f"resume_at: {when.isoformat(sep=' ', timespec='seconds')}")

    if is_root():
        print()
        print(info("pf"))
        print(pf_info())
        print()
        print(info("pf anchor rules"))
        rules = anchor_rules()
        print(rules if rules else dim("(none)"))
    else:
        print()
        print(warning("Run 'sudo macblock status' for PF details"))

    r = run(["/usr/bin/pgrep", "-x", "dnsmasq"])
    if r.returncode == 0:
        print()
        print("dnsmasq: " + success("running"))
    else:
        print()
        print("dnsmasq: " + warning("not running or not visible"))

    return 0
