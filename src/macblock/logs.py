from __future__ import annotations

import sys
import time
from pathlib import Path

from macblock.colors import Colors
from macblock.constants import SYSTEM_LOG_DIR
from macblock.errors import MacblockError


_VALID_STREAMS = {"auto", "stdout", "stderr"}


def _log_paths(component: str) -> dict[str, Path]:
    component = component.strip().lower()

    if component == "dnsmasq":
        return {
            "stdout": SYSTEM_LOG_DIR / "dnsmasq.out.log",
            "stderr": SYSTEM_LOG_DIR / "dnsmasq.err.log",
            # Legacy/unexpected fallback. Current installs should not write this.
            "facility": SYSTEM_LOG_DIR / "dnsmasq.log",
        }

    if component == "daemon":
        return {
            "stdout": SYSTEM_LOG_DIR / "daemon.out.log",
            "stderr": SYSTEM_LOG_DIR / "daemon.err.log",
        }

    raise MacblockError(f"unknown log component: {component}")


def _path_stat(path: Path) -> tuple[int, float] | None:
    try:
        st = path.stat()
        return st.st_size, st.st_mtime
    except FileNotFoundError:
        return None
    except PermissionError:
        return None
    except OSError:
        return None


def _choose_auto_stream(paths: dict[str, Path]) -> str:
    stdout = paths.get("stdout")
    stderr = paths.get("stderr")

    if stdout is None or stderr is None:
        return "stdout" if stdout is not None else "stderr"

    stdout_stat = _path_stat(stdout)
    stderr_stat = _path_stat(stderr)

    # Prefer non-empty files.
    if stdout_stat and stderr_stat:
        stdout_size, stdout_mtime = stdout_stat
        stderr_size, stderr_mtime = stderr_stat

        if stdout_size > 0 and stderr_size == 0:
            return "stdout"
        if stderr_size > 0 and stdout_size == 0:
            return "stderr"

        # Tie-breaker: newest mtime, then bigger size.
        if stderr_mtime != stdout_mtime:
            return "stderr" if stderr_mtime > stdout_mtime else "stdout"
        return "stderr" if stderr_size >= stdout_size else "stdout"

    if stderr_stat and not stdout_stat:
        return "stderr"
    if stdout_stat and not stderr_stat:
        return "stdout"

    # Neither exists/readable: default to stderr (daemon + dnsmasq commonly log there).
    return "stderr"


def _resolve_log_path(
    *, component: str, stream: str, stderr: bool
) -> tuple[Path, str, list[Path]]:
    if stderr:
        stream = "stderr"

    stream = (stream or "auto").strip().lower()
    if stream not in _VALID_STREAMS:
        raise MacblockError(f"invalid stream: {stream} (expected: auto|stdout|stderr)")

    paths = _log_paths(component)

    if stream == "auto":
        chosen = _choose_auto_stream(paths)
    else:
        chosen = stream

    primary = paths.get(chosen)
    if primary is None:
        raise MacblockError(f"invalid stream {chosen} for component {component}")

    alternates: list[Path] = []
    other = "stderr" if chosen == "stdout" else "stdout"
    other_path = paths.get(other)
    if other_path is not None:
        alternates.append(other_path)

    # dnsmasq legacy fallback
    facility = paths.get("facility")
    if facility is not None:
        alternates.append(facility)

    return primary, chosen, alternates


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
    """Read the last N lines from a file without loading whole file."""
    if count <= 0:
        return []

    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            pos = f.tell()

            buf = b""
            block = 8192
            while pos > 0 and buf.count(b"\n") <= count:
                read_size = block if pos >= block else pos
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size)
                buf = chunk + buf

            lines_b = buf.splitlines(keepends=True)[-count:]
            return [b.decode("utf-8", errors="replace") for b in lines_b]
    except FileNotFoundError:
        raise MacblockError(f"log file not found: {path}")
    except PermissionError:
        raise MacblockError(f"permission denied reading: {path}")


def _print_no_logs_hint(component: str, resolved_stream: str) -> None:
    if component == "daemon" and resolved_stream != "stderr":
        print("\nHint: The daemon writes most logs to stderr.", file=sys.stderr)
        print("Hint: Try '--stream stderr' (or '--stderr').", file=sys.stderr)

    if component == "dnsmasq" and resolved_stream != "stderr":
        print(
            "\nHint: dnsmasq logs are usually written to stderr (log-facility=-).",
            file=sys.stderr,
        )
        print("Hint: Try '--stream stderr' (or '--stderr').", file=sys.stderr)

    if component == "dnsmasq":
        print(
            "Hint: Query logs require enabling 'log-queries' in dnsmasq.conf.",
            file=sys.stderr,
        )


def show_logs(
    *,
    component: str,
    lines: int,
    follow: bool,
    stderr: bool,
    stream: str = "auto",
) -> int:
    """Display log output for a component.

    Args:
        component: Which component's logs to show ("daemon" or "dnsmasq")
        lines: Number of lines to display
        follow: If True, continuously follow the log (like tail -f)
        stderr: Backwards-compatible flag to show stderr
        stream: Which stream to show: auto|stdout|stderr

    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        path, resolved_stream, alternates = _resolve_log_path(
            component=component, stream=stream, stderr=stderr
        )
    except MacblockError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    candidate_paths = [path, *alternates]

    chosen_path: Path | None = None
    chosen_lines: list[str] | None = None

    for p in candidate_paths:
        if not p.exists():
            continue

        try:
            log_lines = _tail_lines(p, lines)
        except MacblockError:
            continue

        if log_lines:
            chosen_path = p
            chosen_lines = log_lines
            break

    if chosen_path is None or chosen_lines is None:
        # Keep the old messaging style but make it more actionable.
        print(f"No logs found for {component}.", file=sys.stderr)
        print(f"Tried: {', '.join(str(p) for p in candidate_paths)}", file=sys.stderr)
        _print_no_logs_hint(component.strip().lower(), resolved_stream)
        return 0

    # Print initial lines with colorization
    for line in chosen_lines:
        print(_colorize_line(line), end="")

    sys.stdout.flush()

    if not follow:
        return 0

    print(f"\n--- Following {chosen_path} (Ctrl+C to stop) ---\n", file=sys.stderr)
    sys.stderr.flush()

    try:
        f = chosen_path.open("r", encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise MacblockError(f"log file not found: {chosen_path}")
    except PermissionError:
        raise MacblockError(f"permission denied reading: {chosen_path}")

    try:
        with f:
            f.seek(0, 2)
            while True:
                chunk = f.read()
                if chunk:
                    for line in chunk.splitlines(keepends=True):
                        print(_colorize_line(line), end="")
                    sys.stdout.flush()
                time.sleep(0.25)
    except KeyboardInterrupt:
        print("\n", file=sys.stderr)
        return 0
