from __future__ import annotations

from macblock.constants import (
    DNSMASQ_LISTEN_ADDR,
    DNSMASQ_LISTEN_PORT,
    DNSMASQ_USER,
    SYSTEM_BLOCKLIST_FILE,
    SYSTEM_DNSMASQ_CONF,
    VAR_DB_DNSMASQ_PID,
    VAR_DB_UPSTREAM_CONF,
)


def render_dnsmasq_conf() -> str:
    lines = [
        "keep-in-foreground",
        f"listen-address={DNSMASQ_LISTEN_ADDR}",
        f"port={DNSMASQ_LISTEN_PORT}",
        "bind-interfaces",
        "no-resolv",
        "no-hosts",
        "domain-needed",
        "bogus-priv",
        "cache-size=10000",
        f"user={DNSMASQ_USER}",
        "log-facility=-",
        f"pid-file={VAR_DB_DNSMASQ_PID}",
        f"servers-file={VAR_DB_UPSTREAM_CONF}",
        f"conf-file={SYSTEM_BLOCKLIST_FILE}",
    ]
    return "\n".join(lines) + "\n"


def dnsmasq_conf_path():
    return SYSTEM_DNSMASQ_CONF
