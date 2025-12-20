#!/usr/bin/python3

import re
import subprocess
from pathlib import Path


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def parse_scutil_dns(text: str) -> tuple[list[str], dict[str, list[str]]]:
    current_domain: str | None = None
    defaults: list[str] = []
    per_domain: dict[str, list[str]] = {}

    in_resolver = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m = re.match(r"resolver #\d+", line)
        if m:
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

    return defaults, per_domain


def render_upstream_conf(defaults: list[str], per_domain: dict[str, list[str]]) -> str:
    lines: list[str] = []
    for ip in defaults:
        lines.append(f"server={ip}")

    for dom, ips in sorted(per_domain.items()):
        for ip in ips:
            lines.append(f"server=/{dom}/{ip}")

    return "\n".join(lines) + "\n"


def main() -> int:
    out_path = Path("{{UPSTREAM_OUT}}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    r = run(["/usr/sbin/scutil", "--dns"])
    if r.returncode != 0:
        return r.returncode

    defaults, per_domain = parse_scutil_dns(r.stdout)
    conf = render_upstream_conf(defaults, per_domain)

    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(conf, encoding="utf-8")
    tmp.replace(out_path)

    pid = Path("{{DNSMASQ_PID_FILE}}")
    if pid.exists():
        try:
            p = int(pid.read_text(encoding="utf-8").strip())
        except Exception:
            return 0
        run(["/bin/kill", "-HUP", str(p)])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
