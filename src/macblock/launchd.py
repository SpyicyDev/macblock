from __future__ import annotations

from pathlib import Path

from macblock.errors import MacblockError
from macblock.exec import run

LAUNCHCTL_TIMEOUT = 30.0


def _launchctl(args: list[str], ignore_errors: bool = False) -> None:
    r = run(["/bin/launchctl", *args], timeout=LAUNCHCTL_TIMEOUT)
    if r.returncode != 0 and not ignore_errors:
        msg = r.stderr.strip() or r.stdout.strip() or "launchctl failed"
        raise MacblockError(msg)


def bootstrap_system(plist: Path) -> None:
    _launchctl(["bootstrap", "system", str(plist)])


def bootout_system(plist: Path, ignore_errors: bool = False) -> None:
    _launchctl(["bootout", "system", str(plist)], ignore_errors=ignore_errors)


def bootout_label(label: str, ignore_errors: bool = False) -> None:
    _launchctl(["bootout", f"system/{label}"], ignore_errors=ignore_errors)


def enable_service(label: str) -> None:
    _launchctl(["enable", f"system/{label}"])


def disable_service(label: str) -> None:
    _launchctl(["disable", f"system/{label}"])


def kickstart(label: str) -> None:
    _launchctl(["kickstart", "-k", f"system/{label}"])


def service_exists(label: str) -> bool:
    r = run(["/bin/launchctl", "print", f"system/{label}"], timeout=LAUNCHCTL_TIMEOUT)
    return r.returncode == 0
