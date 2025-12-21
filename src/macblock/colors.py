from __future__ import annotations

import sys


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


def color(text: str, *styles: str) -> str:
    if not sys.stdout.isatty():
        return text
    return "".join(styles) + text + Colors.RESET


def success(text: str) -> str:
    return color(text, Colors.GREEN)


def error(text: str) -> str:
    return color(text, Colors.RED)


def warning(text: str) -> str:
    return color(text, Colors.YELLOW)


def info(text: str) -> str:
    return color(text, Colors.CYAN)


def bold(text: str) -> str:
    return color(text, Colors.BOLD)


def dim(text: str) -> str:
    return color(text, Colors.DIM)


def print_success(text: str) -> None:
    print(success(text))


def print_warning(text: str) -> None:
    print(warning(text))


def print_info(text: str) -> None:
    print(info(text))


def print_error(text: str) -> None:
    print(error(text), file=sys.stderr)
