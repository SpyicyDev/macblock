from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


def run(cmd: list[str], *, timeout: float | None = 10.0) -> RunResult:
    try:
        p = subprocess.run(
            cmd,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        if isinstance(e.stdout, bytes):
            stdout = e.stdout.decode("utf-8", errors="replace")
        else:
            stdout = e.stdout or ""

        if isinstance(e.stderr, bytes):
            stderr = e.stderr.decode("utf-8", errors="replace")
        else:
            stderr = e.stderr or ""

        suffix = f"command timed out after {timeout:.1f}s"
        msg = (stderr.strip() + "\n" + suffix).strip() if stderr.strip() else suffix
        return RunResult(returncode=124, stdout=stdout, stderr=msg)

    return RunResult(returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
