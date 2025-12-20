from __future__ import annotations

from macblock.colors import bold, error, info, success, warning
from macblock.constants import (
    APP_LABEL,
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
    VAR_DB_UPSTREAM_CONF,
)
from macblock.exec import run
from macblock.platform import is_root
from macblock.pf import validate_pf_conf


def _check_file(path) -> tuple[bool, str]:
    ok = path.exists()
    return ok, str(path)


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
        print(info("dnsmasq: ") + success("running"))
    else:
        print(info("dnsmasq: ") + warning("not running or not visible"))

    print(info("label: ") + APP_LABEL)

    return 0 if ok_all else 1
