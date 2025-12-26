from __future__ import annotations

import sys
import time
from pathlib import Path

from macblock.colors import Colors
from macblock.constants import SYSTEM_LOG_DIR
from macblock.errors import MacblockError


def _log_path(component: str, stderr: bool) -> Path:
    """Get the path to a log file for the given component."""
    component = component.strip().lower()

    if component == "dnsmasq":
        if stderr:
            return SYSTEM_LOG_DIR / "dnsmasq.err.log"

        stdout_path = SYSTEM_LOG_DIR / "dnsmasq.out.log"
        facility_path = SYSTEM_LOG_DIR / "dnsmasq.log"
        return stdout_path if stdout_path.exists() else facility_path

    if component == "daemon":
        name = "daemon.err.log" if stderr else "daemon.out.log"
        return SYSTEM_LOG_DIR / name

    raise MacblockError(f"unknown log component: {component}")


def _colorize_line(line: str) -> str:
    """Apply color to log line based on content."""
    if not sys.stdout.isatty():
        return line

    line_lower = line.lower()

    # Error indicators
    if any(
        kw in line_lower for kw in ("error", "fail", "fatal", "exception", "traceback")
    ):
        return f"{Colors.RED}{line}{Colors.RESET}"

    # Warning indicators
    if any(kw in line_lower for kw in ("warn", "warning", "caution")):
        return f"{Colors.YELLOW}{line}{Colors.RESET}"

    # Success/info indicators
    if any(kw in line_lower for kw in ("success", "started", "ready", "enabled")):
        return f"{Colors.GREEN}{line}{Colors.RESET}"

    return line


def _tail_lines(path: Path, count: int) -> list[str]:
    """Read the last N lines from a file."""
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
    """Display log output for a component.

    Args:
        component: Which component's logs to show ("daemon" or "dnsmasq")
        lines: Number of lines to display
        follow: If True, continuously follow the log (like tail -f)
        stderr: If True, show stderr log instead of stdout

    Returns:
        Exit code (0 for success, 1 for error)
    """
    path = _log_path(component, stderr)

    # Check if file exists
    if not path.exists():
        print(f"Log file not found: {path}", file=sys.stderr)
        print(f"The {component} service may not have started yet.", file=sys.stderr)
        print(
            "\nHint: Run 'sudo macblock install' to set up the service.",
            file=sys.stderr,
        )
        return 1

    # Read and display lines
    try:
        log_lines = _tail_lines(path, lines)
    except MacblockError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if not log_lines:
        stream_type = "stderr" if stderr else "stdout"
        print(f"No logs found in {component} {stream_type}.", file=sys.stderr)
        print(f"Log file: {path}", file=sys.stderr)
        if not stderr:
            print("\nHint: Try '--stderr' to view error logs instead.", file=sys.stderr)
        return 0

    # Print initial lines with colorization
    for line in log_lines:
        print(_colorize_line(line), end="")

    sys.stdout.flush()

    if not follow:
        return 0

    # Follow mode
    print(f"\n--- Following {path} (Ctrl+C to stop) ---\n", file=sys.stderr)
    sys.stderr.flush()

    try:
        f = path.open("r", encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise MacblockError(f"log file not found: {path}")
    except PermissionError:
        raise MacblockError(f"permission denied reading: {path}")

    try:
        with f:
            # Seek to end of file
            f.seek(0, 2)
            while True:
                chunk = f.read()
                if chunk:
                    # Colorize each line in the chunk
                    for line in chunk.splitlines(keepends=True):
                        print(_colorize_line(line), end="")
                    sys.stdout.flush()
                time.sleep(0.25)
    except KeyboardInterrupt:
        print("\n", file=sys.stderr)
        return 0
