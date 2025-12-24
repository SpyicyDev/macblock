from __future__ import annotations

import re
import shutil
from pathlib import Path

from macblock.colors import bold, error, info, success, warning
from macblock.constants import (
    DNSMASQ_LISTEN_ADDR,
    DNSMASQ_LISTEN_PORT,
    SYSTEM_BLOCKLIST_FILE,
)
from macblock.exec import run


__test__ = False

_ANSWER_RE = re.compile(r"^(\S+)\s+\d+\s+IN\s+A\s+(\S+)", re.MULTILINE)


def _normalize_domain(domain: str) -> str:
    return domain.strip().lower().strip(".")


def _candidate_suffixes(domain: str) -> list[str]:
    dom = _normalize_domain(domain)
    if not dom:
        return []

    parts = [p for p in dom.split(".") if p]
    out: list[str] = []
    for i in range(len(parts)):
        suffix = ".".join(parts[i:])
        if suffix and suffix not in out:
            out.append(suffix)
    return out


def _find_blocklist_match(
    domain: str, *, blocklist_path: Path = SYSTEM_BLOCKLIST_FILE
) -> tuple[str | None, str | None]:
    candidates = _candidate_suffixes(domain)
    if not candidates:
        return None, "invalid domain"

    want = {f"server=/{c}/" for c in candidates}

    try:
        with blocklist_path.open("r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line in want:
                    matched = line[len("server=/") : -1]
                    return matched, None
    except FileNotFoundError:
        return None, f"blocklist not found: {blocklist_path}"
    except PermissionError:
        return None, f"permission denied reading blocklist: {blocklist_path}"
    except OSError as e:
        return None, f"failed to read blocklist: {e}"

    return None, None


def _interpret_result(
    stdout: str,
    domain: str,
    *,
    blocklist_match: str | None,
    blocklist_error: str | None,
) -> tuple[str, str]:
    stdout_lower = stdout.lower()

    if "status: refused" in stdout_lower:
        return "ERROR", "REFUSED - upstream.conf may be empty or dnsmasq misconfigured"

    if "status: servfail" in stdout_lower:
        return "ERROR", "SERVFAIL - upstream DNS failure"

    if "status: nxdomain" in stdout_lower:
        if blocklist_match is not None:
            return "BLOCKED", f"NXDOMAIN (matched block rule: {blocklist_match})"

        if blocklist_error is not None:
            return "UNKNOWN", f"NXDOMAIN (could not read blocklist: {blocklist_error})"

        return "NXDOMAIN", "Domain does not exist (not in blocklist)"

    matches = _ANSWER_RE.findall(stdout)
    if not matches:
        if "status: noerror" in stdout_lower and "answer: 0" in stdout_lower:
            if blocklist_match is not None:
                return (
                    "BLOCKED",
                    f"No answer returned (matched block rule: {blocklist_match})",
                )
            return "UNKNOWN", "No answer returned"
        return "UNKNOWN", "Could not parse dig output"

    domain_norm = _normalize_domain(domain)

    for name, ip in matches:
        name_clean = _normalize_domain(name)
        if domain_norm and (domain_norm in name_clean or name_clean in domain_norm):
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

    blocklist_match, blocklist_error = _find_blocklist_match(domain)

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

    status, explanation = _interpret_result(
        r.stdout,
        domain,
        blocklist_match=blocklist_match,
        blocklist_error=blocklist_error,
    )
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
