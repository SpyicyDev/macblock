from __future__ import annotations

import re
from dataclasses import dataclass

from macblock.exec import run


@dataclass(frozen=True)
class Resolvers:
    defaults: list[str]
    per_domain: dict[str, list[str]]


def parse_scutil_dns(text: str) -> Resolvers:
    current_domain: str | None = None
    defaults: list[str] = []
    per_domain: dict[str, list[str]] = {}

    in_resolver = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if re.match(r"resolver #\d+", line):
            in_resolver = True
            current_domain = None
            continue

        if not in_resolver:
            continue

        if line.startswith("domain"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                dom = parts[1].strip().strip(".")
                if dom:
                    current_domain = dom
                    per_domain.setdefault(dom, [])
            continue

        if line.startswith("nameserver"):
            parts = line.split(":", 1)
            if len(parts) != 2:
                continue
            ip = parts[1].strip()
            if ip in {"127.0.0.1", "::1", "0.0.0.0", "::"}:
                continue
            if current_domain is None:
                if ip not in defaults:
                    defaults.append(ip)
            else:
                lst = per_domain.setdefault(current_domain, [])
                if ip not in lst:
                    lst.append(ip)

    return Resolvers(defaults=defaults, per_domain=per_domain)


def read_system_resolvers() -> Resolvers:
    r = run(["/usr/sbin/scutil", "--dns"])
    return parse_scutil_dns(r.stdout if r.returncode == 0 else "")


def render_dnsmasq_upstreams(resolvers: Resolvers) -> str:
    lines: list[str] = []
    for ip in resolvers.defaults:
        lines.append(f"server={ip}")

    for dom, ips in sorted(resolvers.per_domain.items()):
        for ip in ips:
            lines.append(f"server=/{dom}/{ip}")

    return "\n".join(lines) + "\n"
