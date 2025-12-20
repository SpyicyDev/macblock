from __future__ import annotations

from importlib import resources


def read_template(name: str) -> str:
    return resources.files("macblock").joinpath("templates", name).read_text(encoding="utf-8")
