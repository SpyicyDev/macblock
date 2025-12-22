from __future__ import annotations

from pathlib import Path

from macblock.blocklists import compile_blocklist, normalize_domain, reload_dnsmasq
from macblock.colors import print_success
from macblock.constants import (
    SYSTEM_BLACKLIST_FILE,
    SYSTEM_BLOCKLIST_FILE,
    SYSTEM_RAW_BLOCKLIST_FILE,
    SYSTEM_WHITELIST_FILE,
)
from macblock.errors import MacblockError


def _read_set(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.add(s)
    return out


def _write_set(path: Path, values: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(sorted(values))
    path.write_text(text + ("\n" if text else ""), encoding="utf-8")


def _recompile() -> int:
    if not SYSTEM_RAW_BLOCKLIST_FILE.exists():
        raise MacblockError("blocklist not downloaded; run: sudo macblock update")
    count = compile_blocklist(
        SYSTEM_RAW_BLOCKLIST_FILE,
        SYSTEM_WHITELIST_FILE,
        SYSTEM_BLACKLIST_FILE,
        SYSTEM_BLOCKLIST_FILE,
    )
    reload_dnsmasq()
    return count


def add_whitelist(domain: str) -> int:
    d = normalize_domain(domain)
    values = {normalize_domain(x) for x in _read_set(SYSTEM_WHITELIST_FILE)}
    values.add(d)
    _write_set(SYSTEM_WHITELIST_FILE, values)
    _recompile()
    print_success(f"allowed: {d}")
    return 0


def remove_whitelist(domain: str) -> int:
    d = normalize_domain(domain)
    values = {normalize_domain(x) for x in _read_set(SYSTEM_WHITELIST_FILE)}
    values.discard(d)
    _write_set(SYSTEM_WHITELIST_FILE, values)
    _recompile()
    print_success(f"removed: {d}")
    return 0


def list_whitelist() -> int:
    values = sorted({normalize_domain(x) for x in _read_set(SYSTEM_WHITELIST_FILE)})
    for v in values:
        print(v)
    return 0


def add_blacklist(domain: str) -> int:
    d = normalize_domain(domain)
    values = {normalize_domain(x) for x in _read_set(SYSTEM_BLACKLIST_FILE)}
    values.add(d)
    _write_set(SYSTEM_BLACKLIST_FILE, values)
    _recompile()
    print_success(f"denied: {d}")
    return 0


def remove_blacklist(domain: str) -> int:
    d = normalize_domain(domain)
    values = {normalize_domain(x) for x in _read_set(SYSTEM_BLACKLIST_FILE)}
    values.discard(d)
    _write_set(SYSTEM_BLACKLIST_FILE, values)
    _recompile()
    print_success(f"removed: {d}")
    return 0


def list_blacklist() -> int:
    values = sorted({normalize_domain(x) for x in _read_set(SYSTEM_BLACKLIST_FILE)})
    for v in values:
        print(v)
    return 0
