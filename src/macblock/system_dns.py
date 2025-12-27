from __future__ import annotations

import re
from dataclasses import dataclass

from macblock.exec import run


_LOCALHOST_DNS_V4 = ["127.0.0.1"]


@dataclass(frozen=True)
class ServiceDnsBackup:
    dns_servers: list[str] | None
    search_domains: list[str] | None
    dhcp_dns_servers: list[str] | None = None


@dataclass(frozen=True)
class ServiceInfo:
    name: str
    device: str | None


def _parse_networksetup_listallnetworkservices(text: str) -> list[str]:
    services: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        if line.startswith("An asterisk"):
            continue
        if line.startswith("*"):
            continue
        services.append(line.strip())
    return services


def _parse_networksetup_listnetworkserviceorder(text: str) -> dict[str, str | None]:
    mapping: dict[str, str | None] = {}
    current_service: str | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        m = re.match(r"^\(\d+\)\s+(.*)$", line)
        if m:
            current_service = m.group(1).strip()
            if current_service and current_service not in mapping:
                mapping[current_service] = None
            continue

        if current_service is None:
            continue

        m = re.search(r"Device:\s*([^\)]*)\)", line)
        if m:
            device = m.group(1).strip()
            mapping[current_service] = device or None

    return mapping


def list_enabled_network_services() -> list[str]:
    r = run(["/usr/sbin/networksetup", "-listallnetworkservices"])
    if r.returncode != 0:
        return []
    return _parse_networksetup_listallnetworkservices(r.stdout)


def list_network_service_devices() -> dict[str, str | None]:
    r = run(["/usr/sbin/networksetup", "-listnetworkserviceorder"])
    if r.returncode != 0:
        return {}
    return _parse_networksetup_listnetworkserviceorder(r.stdout)


def _parse_getinfo_device(text: str) -> str | None:
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("Device:"):
            continue
        device = line.split(":", 1)[1].strip()
        return device or None
    return None


def get_service_info(service: str) -> ServiceInfo:
    device = list_network_service_devices().get(service)
    if device is None:
        r = run(["/usr/sbin/networksetup", "-getinfo", service])
        device = _parse_getinfo_device(r.stdout if r.returncode == 0 else "")
    return ServiceInfo(name=service, device=device)


def _parse_getdnsservers(text: str) -> list[str] | None:
    out = text.strip()
    if not out:
        return None

    if "There aren't any DNS Servers" in out:
        return None

    servers: list[str] = []
    for raw in out.splitlines():
        ip = raw.strip()
        if not ip:
            continue
        servers.append(ip)
    return servers or None


def get_dns_servers(service: str) -> list[str] | None:
    r = run(["/usr/sbin/networksetup", "-getdnsservers", service])
    return _parse_getdnsservers(r.stdout if r.returncode == 0 else "")


def set_dns_servers(service: str, servers: list[str] | None) -> bool:
    if servers:
        args = ["/usr/sbin/networksetup", "-setdnsservers", service, *servers]
    else:
        args = ["/usr/sbin/networksetup", "-setdnsservers", service, "Empty"]
    r = run(args)
    return r.returncode == 0


def _parse_getsearchdomains(text: str) -> list[str] | None:
    out = text.strip()
    if not out:
        return None

    if "There aren't any Search Domains" in out:
        return None

    domains: list[str] = []
    for raw in out.splitlines():
        dom = raw.strip().strip(".")
        if dom:
            domains.append(dom)
    return domains or None


def get_search_domains(service: str) -> list[str] | None:
    r = run(["/usr/sbin/networksetup", "-getsearchdomains", service])
    return _parse_getsearchdomains(r.stdout if r.returncode == 0 else "")


def set_search_domains(service: str, domains: list[str] | None) -> bool:
    if domains:
        args = ["/usr/sbin/networksetup", "-setsearchdomains", service, *domains]
    else:
        args = ["/usr/sbin/networksetup", "-setsearchdomains", service, "Empty"]
    r = run(args)
    return r.returncode == 0


def is_localhost_dns(servers: list[str] | None) -> bool:
    return servers == _LOCALHOST_DNS_V4


def compute_managed_services(*, exclude: set[str] | None = None) -> list[ServiceInfo]:
    exclude = exclude or set()

    managed: list[ServiceInfo] = []
    device_map = list_network_service_devices()

    for service in list_enabled_network_services():
        if service in exclude:
            continue

        service_l = service.lower()
        if any(
            x in service_l
            for x in ("vpn", "tailscale", "wireguard", "openvpn", "anyconnect")
        ):
            continue

        device = device_map.get(service)
        if device is None:
            r = run(["/usr/sbin/networksetup", "-getinfo", service])
            device = _parse_getinfo_device(r.stdout if r.returncode == 0 else "")

        info = ServiceInfo(name=service, device=device)
        device_s = device or ""

        if device_s.startswith(("utun", "ppp", "tun", "tap")):
            continue

        if device_s.startswith("en") or device_s.startswith("bridge"):
            managed.append(info)
            continue

        if any(
            x in service_l for x in ("wi-fi", "wifi", "ethernet", "usb", "thunderbolt")
        ):
            managed.append(info)

    return sorted(managed, key=lambda x: x.name.lower())


def snapshot_service_backup(service: str) -> ServiceDnsBackup:
    info = get_service_info(service)
    dhcp = read_dhcp_nameservers(info.device or "")
    return ServiceDnsBackup(
        dns_servers=get_dns_servers(service),
        search_domains=get_search_domains(service),
        dhcp_dns_servers=dhcp or None,
    )


def apply_localhost_dns(service: str) -> bool:
    ok_dns = set_dns_servers(service, _LOCALHOST_DNS_V4)
    return ok_dns


def restore_from_backup(service: str, backup: ServiceDnsBackup) -> bool:
    ok_dns = set_dns_servers(service, backup.dns_servers)
    ok_search = set_search_domains(service, backup.search_domains)
    return ok_dns and ok_search


def parse_exclude_services_file(text: str) -> set[str]:
    exclude: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        exclude.add(line)
    return exclude


_IP_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")


def read_dhcp_nameservers(device: str) -> list[str]:
    if not device:
        return []
    r = run(["/usr/sbin/ipconfig", "getoption", device, "domain_name_server"])
    if r.returncode != 0:
        return []

    ips: list[str] = []
    for token in (r.stdout or "").strip().split():
        if _IP_RE.match(token) and token not in ips and token != "127.0.0.1":
            ips.append(token)
    return ips
