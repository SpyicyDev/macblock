from __future__ import annotations

import time
from pathlib import Path

from macblock.constants import SYSTEM_LOG_DIR
from macblock.errors import MacblockError


def _log_path(component: str, stderr: bool) -> Path:
    component = component.strip().lower()

    if component == "dnsmasq":
        name = "dnsmasq.err.log" if stderr else "dnsmasq.out.log"
        return SYSTEM_LOG_DIR / name

    if component == "daemon":
        name = "daemon.err.log" if stderr else "daemon.out.log"
        return SYSTEM_LOG_DIR / name

    raise MacblockError(f"unknown log component: {component}")


def _tail_lines(path: Path, count: int) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise MacblockError(f"log file not found: {path}")
    except PermissionError:
        raise MacblockError(f"permission denied reading: {path}")

    if count <= 0:
        return []

    lines = text.splitlines(keepends=True)
    return lines[-count:]


def show_logs(*, component: str, lines: int, follow: bool, stderr: bool) -> int:
    path = _log_path(component, stderr)

    for line in _tail_lines(path, lines):
        print(line, end="")

    if not follow:
        return 0

    try:
        f = path.open("r", encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise MacblockError(f"log file not found: {path}")
    except PermissionError:
        raise MacblockError(f"permission denied reading: {path}")

    with f:
        f.seek(0, 2)
        while True:
            chunk = f.read()
            if chunk:
                print(chunk, end="")
            time.sleep(0.25)
