from __future__ import annotations

import time

from macblock.colors import print_success
from macblock.constants import (
    APP_LABEL,
    LAUNCHD_DNSMASQ_PLIST,
    LAUNCHD_STATE_PLIST,
    LAUNCHD_UPSTREAMS_PLIST,
    SYSTEM_DNS_EXCLUDE_SERVICES_FILE,
    SYSTEM_STATE_FILE,
)
from macblock.launchd import bootstrap_system, enable_service, kickstart
from macblock.state import load_state, replace_state, save_state_atomic
from macblock.system_dns import (
    ServiceDnsBackup,
    apply_localhost_dns,
    compute_managed_services,
    is_localhost_dns,
    parse_exclude_services_file,
    restore_from_backup,
    snapshot_service_backup,
)


def _parse_duration_seconds(value: str) -> int:
    value = value.strip().lower()
    if value.endswith("m"):
        return int(value[:-1]) * 60
    if value.endswith("h"):
        return int(value[:-1]) * 60 * 60
    if value.endswith("d"):
        return int(value[:-1]) * 60 * 60 * 24
    raise ValueError("duration must end with m/h/d")


def _ensure_daemon(plist, label: str) -> None:
    try:
        bootstrap_system(plist)
    except Exception:
        pass

    try:
        enable_service(label)
    except Exception:
        pass

    try:
        kickstart(label)
    except Exception:
        pass


def _ensure_daemons() -> None:
    _ensure_daemon(LAUNCHD_UPSTREAMS_PLIST, f"{APP_LABEL}.upstreams")
    _ensure_daemon(LAUNCHD_DNSMASQ_PLIST, f"{APP_LABEL}.dnsmasq")
    _ensure_daemon(LAUNCHD_STATE_PLIST, f"{APP_LABEL}.state")


def _read_excluded_services() -> set[str]:
    if not SYSTEM_DNS_EXCLUDE_SERVICES_FILE.exists():
        return set()
    try:
        text = SYSTEM_DNS_EXCLUDE_SERVICES_FILE.read_text(encoding="utf-8")
    except Exception:
        return set()
    return parse_exclude_services_file(text)


def _to_backup_dict(backup: ServiceDnsBackup) -> dict[str, list[str] | None]:
    return {"dns": backup.dns_servers, "search": backup.search_domains}


def _from_backup_dict(data: dict[str, object]) -> ServiceDnsBackup:
    dns_val = data.get("dns")
    search_val = data.get("search")
    dns = list(dns_val) if isinstance(dns_val, list) else None
    search = list(search_val) if isinstance(search_val, list) else None
    return ServiceDnsBackup(dns_servers=dns, search_domains=search)


def _restore_dns(st) -> None:
    for service in st.managed_services:
        cfg = st.dns_backup.get(service)
        if not isinstance(cfg, dict):
            continue
        restore_from_backup(service, _from_backup_dict(cfg))


def _apply_localhost(st) -> tuple[dict[str, dict[str, list[str] | None]], list[str]]:
    exclude = _read_excluded_services()
    services = compute_managed_services(exclude=exclude)
    service_names = [s.name for s in services]

    dns_backup = dict(st.dns_backup)

    for info in services:
        if info.name not in dns_backup:
            snap = snapshot_service_backup(info.name)
            if not is_localhost_dns(snap.dns_servers):
                dns_backup[info.name] = _to_backup_dict(snap)
        apply_localhost_dns(info.name)

    return dns_backup, service_names


def do_enable() -> int:
    _ensure_daemons()
    st = load_state(SYSTEM_STATE_FILE)
    dns_backup, managed_services = _apply_localhost(st)

    save_state_atomic(
        SYSTEM_STATE_FILE,
        replace_state(
            st,
            enabled=True,
            resume_at_epoch=None,
            dns_backup=dns_backup,
            managed_services=managed_services,
        ),
    )

    print_success("enabled")
    return 0


def do_disable() -> int:
    st = load_state(SYSTEM_STATE_FILE)
    _restore_dns(st)

    save_state_atomic(
        SYSTEM_STATE_FILE,
        replace_state(st, enabled=False, resume_at_epoch=None),
    )

    print_success("disabled")
    return 0


def do_pause(duration: str) -> int:
    _ensure_daemons()
    seconds = _parse_duration_seconds(duration)
    resume_at = int(time.time()) + seconds

    st = load_state(SYSTEM_STATE_FILE)
    _restore_dns(st)

    save_state_atomic(
        SYSTEM_STATE_FILE,
        replace_state(st, enabled=True, resume_at_epoch=resume_at),
    )

    print_success("paused")
    return 0


def do_resume() -> int:
    _ensure_daemons()
    st = load_state(SYSTEM_STATE_FILE)
    dns_backup, managed_services = _apply_localhost(st)

    save_state_atomic(
        SYSTEM_STATE_FILE,
        replace_state(
            st,
            enabled=True,
            resume_at_epoch=None,
            dns_backup=dns_backup,
            managed_services=managed_services,
        ),
    )

    print_success("resumed")
    return 0
