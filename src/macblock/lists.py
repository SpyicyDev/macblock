from __future__ import annotations

import sys
from pathlib import Path

from macblock.blocklists import compile_blocklist, normalize_domain, reload_dnsmasq
from macblock.colors import print_success
from macblock.fs import atomic_write_text
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
    text = "\n".join(sorted(values))
    atomic_write_text(path, text + ("\n" if text else ""), mode=0o644)


def _read_domains_tolerant(path: Path) -> set[str]:
    if not path.exists():
        return set()

    out: set[str] = set()
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        try:
            out.add(normalize_domain(s))
        except MacblockError as e:
            print(
                f"warning: invalid domain in {path.name}:{i}: {s} ({e}); remove/repair this line",
                file=sys.stderr,
            )

    return out


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
    values = _read_domains_tolerant(SYSTEM_WHITELIST_FILE)
    values.add(d)
    _write_set(SYSTEM_WHITELIST_FILE, values)
    _recompile()
    print_success(f"allowed: {d}")
    return 0


def remove_whitelist(domain: str) -> int:
    d = normalize_domain(domain)
    values = _read_domains_tolerant(SYSTEM_WHITELIST_FILE)
    values.discard(d)
    _write_set(SYSTEM_WHITELIST_FILE, values)
    _recompile()
    print_success(f"removed: {d}")
    return 0


def list_whitelist() -> int:
    values = sorted(_read_domains_tolerant(SYSTEM_WHITELIST_FILE))
    for v in values:
        print(v)
    return 0


def add_blacklist(domain: str) -> int:
    d = normalize_domain(domain)
    values = _read_domains_tolerant(SYSTEM_BLACKLIST_FILE)
    values.add(d)
    _write_set(SYSTEM_BLACKLIST_FILE, values)
    _recompile()
    print_success(f"denied: {d}")
    return 0


def remove_blacklist(domain: str) -> int:
    d = normalize_domain(domain)
    values = _read_domains_tolerant(SYSTEM_BLACKLIST_FILE)
    values.discard(d)
    _write_set(SYSTEM_BLACKLIST_FILE, values)
    _recompile()
    print_success(f"removed: {d}")
    return 0


def list_blacklist() -> int:
    values = sorted(_read_domains_tolerant(SYSTEM_BLACKLIST_FILE))
    for v in values:
        print(v)
    return 0
