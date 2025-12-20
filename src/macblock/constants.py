from __future__ import annotations

from pathlib import Path


APP_NAME = "macblock"
APP_ORG = "com.local"
APP_LABEL = f"{APP_ORG}.{APP_NAME}"

DNSMASQ_USER = "_macblockd"

SYSTEM_SUPPORT_DIR = Path("/Library/Application Support") / APP_NAME
SYSTEM_CONFIG_DIR = SYSTEM_SUPPORT_DIR / "etc"
SYSTEM_BIN_DIR = SYSTEM_SUPPORT_DIR / "bin"

SYSTEM_STATE_FILE = SYSTEM_SUPPORT_DIR / "state.json"

SYSTEM_RAW_BLOCKLIST_FILE = SYSTEM_SUPPORT_DIR / "blocklist.raw"
SYSTEM_BLOCKLIST_FILE = SYSTEM_SUPPORT_DIR / "blocklist.conf"
SYSTEM_WHITELIST_FILE = SYSTEM_SUPPORT_DIR / "whitelist.txt"
SYSTEM_BLACKLIST_FILE = SYSTEM_SUPPORT_DIR / "blacklist.txt"

SYSTEM_DNSMASQ_CONF = SYSTEM_CONFIG_DIR / "dnsmasq.conf"

VAR_DB_DIR = Path("/var/db") / APP_NAME
VAR_DB_UPSTREAM_CONF = VAR_DB_DIR / "upstream.conf"
VAR_DB_DNSMASQ_PID = VAR_DB_DIR / "dnsmasq.pid"

SYSTEM_LOG_DIR = Path("/Library/Logs") / APP_NAME

LAUNCHD_DIR = Path("/Library/LaunchDaemons")
LAUNCHD_DNSMASQ_PLIST = LAUNCHD_DIR / f"{APP_LABEL}.dnsmasq.plist"
LAUNCHD_UPSTREAMS_PLIST = LAUNCHD_DIR / f"{APP_LABEL}.upstreams.plist"
LAUNCHD_PF_PLIST = LAUNCHD_DIR / f"{APP_LABEL}.pf.plist"

PF_ANCHOR_DIR = Path("/etc/pf.anchors")
PF_ANCHOR_FILE = PF_ANCHOR_DIR / APP_LABEL
PF_CONF = Path("/etc/pf.conf")
PF_LOCK_FILE = SYSTEM_SUPPORT_DIR / "pf.lock"
PF_EXCLUDE_INTERFACES_FILE = SYSTEM_SUPPORT_DIR / "pf.exclude_interfaces"

DNSMASQ_LISTEN_ADDR = "127.0.0.1"
DNSMASQ_LISTEN_ADDR_V6 = "::1"
DNSMASQ_LISTEN_PORT = 5353

BLOCKLIST_SOURCES = {
    "stevenblack": {
        "name": "StevenBlack Unified",
        "url": "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
    },
    "stevenblack-fakenews": {
        "name": "StevenBlack + Fakenews",
        "url": "https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/fakenews/hosts",
    },
    "stevenblack-gambling": {
        "name": "StevenBlack + Gambling",
        "url": "https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/gambling/hosts",
    },
    "hagezi-pro": {
        "name": "HaGeZi Pro",
        "url": "https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/hosts/pro.txt",
    },
    "hagezi-ultimate": {
        "name": "HaGeZi Ultimate",
        "url": "https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/hosts/ultimate.txt",
    },
    "oisd-small": {
        "name": "OISD Small",
        "url": "https://small.oisd.nl/hosts",
    },
    "oisd-big": {
        "name": "OISD Big",
        "url": "https://big.oisd.nl/hosts",
    },
}

DEFAULT_BLOCKLIST_SOURCE = "stevenblack"
