from __future__ import annotations

import re
import shutil

from macblock.colors import bold, error, info, success, warning
from macblock.constants import DNSMASQ_LISTEN_ADDR, DNSMASQ_LISTEN_PORT
from macblock.exec import run


__test__ = False

_ANSWER_RE = re.compile(r"^(\S+)\s+\d+\s+IN\s+A\s+(\S+)", re.MULTILINE)


def _interpret_result(stdout: str, domain: str) -> tuple[str, str]:
    stdout_lower = stdout.lower()

    if "status: refused" in stdout_lower:
        return "ERROR", "REFUSED - upstream.conf may be empty or dnsmasq misconfigured"

    if "status: servfail" in stdout_lower:
        return "ERROR", "SERVFAIL - upstream DNS failure"

    if "status: nxdomain" in stdout_lower:
        return "NXDOMAIN", "Domain does not exist"

    matches = _ANSWER_RE.findall(stdout)
    if not matches:
        if "status: noerror" in stdout_lower and "answer: 0" in stdout_lower:
            return "BLOCKED", "No answer returned (sinkholed)"
        return "UNKNOWN", "Could not parse dig output"

    for name, ip in matches:
        name_clean = name.rstrip(".").lower()
        if domain.lower() in name_clean or name_clean in domain.lower():
            if ip in ("0.0.0.0", "127.0.0.1", "::"):
                return "BLOCKED", f"Resolved to sinkhole IP {ip}"
            return "ALLOWED", f"Resolved to {ip}"

    first_ip = matches[0][1]
    if first_ip in ("0.0.0.0", "127.0.0.1", "::"):
        return "BLOCKED", f"Resolved to sinkhole IP {first_ip}"
    return "ALLOWED", f"Resolved to {first_ip}"


def test_domain(domain: str) -> int:
    dig = shutil.which("dig")
    if dig is None:
        print(
            error(
                "dig not found; install bind tools or use 'scutil --dns' and a browser test"
            )
        )
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

    status, explanation = _interpret_result(r.stdout, domain)
    print()
    if status == "BLOCKED":
        print(success(f"[{status}]") + f" {explanation}")
    elif status == "ALLOWED":
        print(warning(f"[{status}]") + f" {explanation}")
    elif status == "ERROR":
        print(error(f"[{status}]") + f" {explanation}")
    else:
        print(info(f"[{status}]") + f" {explanation}")

    return 0
