#!/usr/bin/python3

import subprocess
import sys


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main() -> int:
    pfctl = "/sbin/pfctl"

    r1 = run([pfctl, "-E"])
    if r1.returncode not in (0, 1):
        sys.stderr.write(r1.stderr)
        return r1.returncode

    r2 = run([pfctl, "-f", "/etc/pf.conf"])
    if r2.returncode != 0:
        sys.stderr.write(r2.stderr)
        return r2.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
