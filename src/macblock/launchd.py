from __future__ import annotations

from pathlib import Path

from macblock.errors import MacblockError
from macblock.exec import run


def _launchctl(args: list[str]) -> None:
    r = run(["/bin/launchctl", *args])
    if r.returncode != 0:
        msg = r.stderr.strip() or r.stdout.strip() or "launchctl failed"
        raise MacblockError(msg)


def bootstrap_system(plist: Path) -> None:
    _launchctl(["bootstrap", "system", str(plist)])


def bootout_system(plist: Path) -> None:
    _launchctl(["bootout", "system", str(plist)])


def enable_service(label: str) -> None:
    _launchctl(["enable", f"system/{label}"])


def disable_service(label: str) -> None:
    _launchctl(["disable", f"system/{label}"])


def kickstart(label: str) -> None:
    _launchctl(["kickstart", "-k", f"system/{label}"])


def service_exists(label: str) -> bool:
    r = run(["/bin/launchctl", "print", f"system/{label}"])
    return r.returncode == 0
