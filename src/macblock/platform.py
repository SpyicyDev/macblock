import os
import sys

from macblock.errors import UnsupportedPlatformError


def require_macos() -> None:
    if sys.platform != "darwin":
        raise UnsupportedPlatformError(f"Unsupported platform: {sys.platform}")


def is_root() -> bool:
    if hasattr(os, "geteuid"):
        return os.geteuid() == 0
    return False
