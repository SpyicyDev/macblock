import os
from pathlib import Path

import pytest

import macblock.fs as mbfs


def test_atomic_write_text_does_not_use_deterministic_tmp(tmp_path) -> None:
    target = tmp_path / "state.json"
    deterministic_tmp = target.with_suffix(target.suffix + ".tmp")
    deterministic_tmp.mkdir()

    mbfs.atomic_write_text(target, "hello\n", mode=0o644)
    assert target.read_text(encoding="utf-8") == "hello\n"


def test_atomic_write_text_chmods_temp_before_replace(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[tuple[str, Path, Path | None]] = []

    original_replace = mbfs.os.replace
    original_chmod = mbfs.os.chmod

    def _chmod(p: str | os.PathLike[str], m: int):
        events.append(("chmod", Path(os.fspath(p)), None))
        return original_chmod(os.fspath(p), m)

    def _replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]):
        events.append(("replace", Path(os.fspath(src)), Path(os.fspath(dst))))
        return original_replace(os.fspath(src), os.fspath(dst))

    monkeypatch.setattr(mbfs.os, "chmod", _chmod)
    monkeypatch.setattr(mbfs.os, "replace", _replace)

    target = tmp_path / "mode.txt"
    mbfs.atomic_write_text(target, "hi\n", mode=0o644)

    assert [e[0] for e in events] == ["chmod", "replace"]
    assert events[0][1] != target
    assert events[1][2] == target
    assert (target.stat().st_mode & 0o777) == 0o644


def test_atomic_write_text_cleans_up_temp_on_replace_failure(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "cleanup.txt"

    def _replace(_src: object, _dst: object):
        raise OSError("boom")

    monkeypatch.setattr(mbfs.os, "replace", _replace)

    with pytest.raises(OSError, match=r"boom"):
        mbfs.atomic_write_text(target, "hi\n", mode=0o644)

    leftovers = [
        p
        for p in tmp_path.iterdir()
        if p.name.startswith(f".{target.name}.") and p.name.endswith(".tmp")
    ]
    assert leftovers == []
