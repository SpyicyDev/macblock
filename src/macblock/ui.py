from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterator

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
SPINNER_INTERVAL = 0.08


class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def _is_tty() -> bool:
    return sys.stdout.isatty()


def _color(text: str, *styles: str) -> str:
    if not _is_tty():
        return text
    return "".join(styles) + text + Colors.RESET


def green(text: str) -> str:
    return _color(text, Colors.GREEN)


def red(text: str) -> str:
    return _color(text, Colors.RED)


def yellow(text: str) -> str:
    return _color(text, Colors.YELLOW)


def cyan(text: str) -> str:
    return _color(text, Colors.CYAN)


def bold(text: str) -> str:
    return _color(text, Colors.BOLD)


def dim(text: str) -> str:
    return _color(text, Colors.DIM)


def success(text: str) -> str:
    return green(text)


def error(text: str) -> str:
    return red(text)


def warning(text: str) -> str:
    return yellow(text)


def info(text: str) -> str:
    return cyan(text)


SYMBOL_OK = "✓"
SYMBOL_FAIL = "✗"
SYMBOL_WARN = "⚠"
SYMBOL_BULLET = "•"
SYMBOL_ARROW = "→"
SYMBOL_ACTIVE = "●"
SYMBOL_INACTIVE = "○"


def header(emoji: str, title: str) -> None:
    print(f"\n{emoji} {bold(title)}\n")


def subheader(title: str) -> None:
    print(f"\n{bold(title)}")


def step(msg: str) -> None:
    print(f"  {dim(SYMBOL_BULLET)} {msg}")


def step_done(msg: str) -> None:
    print(f"  {green(SYMBOL_OK)} {msg}")


def step_fail(msg: str) -> None:
    print(f"  {red(SYMBOL_FAIL)} {msg}", file=sys.stderr)


def step_warn(msg: str) -> None:
    print(f"  {yellow(SYMBOL_WARN)} {msg}")


def step_skip(msg: str) -> None:
    print(f"  {dim(SYMBOL_BULLET)} {dim(msg)}")


def status_line(label: str, value: str, width: int = 14) -> None:
    print(f"  {label + ':':<{width}} {value}")


def status_ok(label: str, value: str, width: int = 14) -> None:
    print(f"  {label + ':':<{width}} {green(SYMBOL_OK)} {value}")


def status_active(label: str, value: str, width: int = 14) -> None:
    print(f"  {label + ':':<{width}} {green(SYMBOL_ACTIVE)} {value}")


def status_inactive(label: str, value: str, width: int = 14) -> None:
    print(f"  {label + ':':<{width}} {dim(SYMBOL_INACTIVE)} {value}")


def status_warn(label: str, value: str, width: int = 14) -> None:
    print(f"  {label + ':':<{width}} {yellow(SYMBOL_WARN)} {value}")


def status_err(label: str, value: str, width: int = 14) -> None:
    print(f"  {label + ':':<{width}} {red(SYMBOL_FAIL)} {value}")


def status_info(label: str, value: str, width: int = 14) -> None:
    print(f"  {label + ':':<{width}} {value}")


def result_success(msg: str) -> None:
    print(f"\n{green(SYMBOL_OK)} {msg}")


def result_fail(msg: str) -> None:
    print(f"\n{red(SYMBOL_FAIL)} {msg}", file=sys.stderr)


def result_warn(msg: str) -> None:
    print(f"\n{yellow(SYMBOL_WARN)} {msg}")


def list_item(text: str, indent: int = 2) -> None:
    print(f"{' ' * indent}{SYMBOL_BULLET} {text}")


def list_item_ok(text: str, indent: int = 2) -> None:
    print(f"{' ' * indent}{green(SYMBOL_OK)} {text}")


def list_item_fail(text: str, indent: int = 2) -> None:
    print(f"{' ' * indent}{red(SYMBOL_FAIL)} {text}")


def list_item_warn(text: str, indent: int = 2) -> None:
    print(f"{' ' * indent}{yellow(SYMBOL_WARN)} {text}")


def dns_status(
    service: str,
    servers: list[str] | None,
    is_active: bool = True,
    is_blocking: bool = False,
) -> None:
    active_symbol = green(SYMBOL_ACTIVE) if is_active else dim(SYMBOL_INACTIVE)

    if servers is None or len(servers) == 0:
        dns_str = dim("DHCP")
    elif servers == ["127.0.0.1"]:
        dns_str = f"{green(SYMBOL_ARROW)} 127.0.0.1" + (
            f" {dim('(blocking)')}" if is_blocking else ""
        )
    else:
        dns_str = ", ".join(servers)

    print(f"  {active_symbol} {service}: {dns_str}")


class Spinner:
    def __init__(self, message: str):
        self.message = message
        self._running = False
        self._thread: threading.Thread | None = None
        self._frame_index = 0
        self._final_message: str | None = None
        self._final_symbol: str | None = None
        self._final_color: str | None = None
        self._lock = threading.Lock()

    def _clear_line(self) -> None:
        if _is_tty():
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

    def _write_frame(self) -> None:
        if _is_tty():
            frame = SPINNER_FRAMES[self._frame_index]
            sys.stdout.write(f"\r{cyan(frame)} {self.message}")
            sys.stdout.flush()

    def _spin(self) -> None:
        while self._running:
            with self._lock:
                if not self._running:
                    break
                self._write_frame()
                self._frame_index = (self._frame_index + 1) % len(SPINNER_FRAMES)
            time.sleep(SPINNER_INTERVAL)

    def start(self) -> "Spinner":
        if not _is_tty():
            print(f"  {SYMBOL_BULLET} {self.message}...")
            return self

        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        with self._lock:
            self._running = False

        if self._thread is not None:
            self._thread.join(timeout=0.5)
            self._thread = None

        if _is_tty():
            self._clear_line()
            if self._final_symbol and self._final_message:
                colored_symbol = (
                    _color(self._final_symbol, self._final_color)
                    if self._final_color
                    else self._final_symbol
                )
                print(f"  {colored_symbol} {self._final_message}")
            elif self._final_message:
                print(f"  {self._final_message}")
        elif self._final_message and self._final_message != self.message:
            symbol = self._final_symbol or SYMBOL_BULLET
            print(f"  {symbol} {self._final_message}")

    def succeed(self, message: str | None = None) -> None:
        self._final_symbol = SYMBOL_OK
        self._final_color = Colors.GREEN
        self._final_message = message or self.message
        self.stop()

    def fail(self, message: str | None = None) -> None:
        self._final_symbol = SYMBOL_FAIL
        self._final_color = Colors.RED
        self._final_message = message or self.message
        self.stop()

    def warn(self, message: str | None = None) -> None:
        self._final_symbol = SYMBOL_WARN
        self._final_color = Colors.YELLOW
        self._final_message = message or self.message
        self.stop()

    def __enter__(self) -> "Spinner":
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self.fail(f"{self.message} - failed")
        elif self._final_symbol is None:
            self.succeed()


@contextmanager
def spinner(message: str) -> Iterator[Spinner]:
    s = Spinner(message)
    s.start()
    try:
        yield s
    except Exception:
        s.fail(f"{message} - failed")
        raise
    else:
        if s._final_symbol is None:
            s.succeed()


def print_success(text: str) -> None:
    print(success(text))


def print_warning(text: str) -> None:
    print(warning(text))


def print_info(text: str) -> None:
    print(info(text))


def print_error(text: str) -> None:
    print(error(text), file=sys.stderr)
