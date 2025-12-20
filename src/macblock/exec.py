from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


def run(cmd: list[str]) -> RunResult:
    p = subprocess.run(
        cmd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return RunResult(returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
