from __future__ import annotations

import shutil

from macblock.colors import bold, error, info
from macblock.constants import DNSMASQ_LISTEN_ADDR, DNSMASQ_LISTEN_PORT
from macblock.exec import run


__test__ = False


def test_domain(domain: str) -> int:
    dig = shutil.which("dig")
    if dig is None:
        print(error("dig not found; install bind tools or use 'scutil --dns' and a browser test"))
        return 1

    print(info("query"))
    print(f"domain: {bold(domain)}")

    r = run(
        [
            dig,
            f"@{DNSMASQ_LISTEN_ADDR}",
            "-p",
            str(DNSMASQ_LISTEN_PORT),
            domain,
            "+time=2",
            "+tries=1",
        ]
    )
    if r.returncode != 0:
        print(error(r.stderr.strip() or "dig failed"))
        return 1

    print(r.stdout.rstrip())
    return 0
