from pathlib import Path

import pytest

import macblock.lists as lists


def test_list_whitelist_tolerates_invalid_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    whitelist = tmp_path / "whitelist.txt"
    whitelist.write_text("good.example\ninvalid@@\n", encoding="utf-8")

    monkeypatch.setattr(lists, "SYSTEM_WHITELIST_FILE", whitelist)

    rc = lists.list_whitelist()
    assert rc == 0

    captured = capsys.readouterr()
    assert captured.out.strip() == "good.example"
    assert "warning:" in captured.err


def test_add_whitelist_skips_invalid_existing_lines_and_writes_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    whitelist = tmp_path / "whitelist.txt"
    whitelist.write_text("invalid@@\n", encoding="utf-8")

    monkeypatch.setattr(lists, "SYSTEM_WHITELIST_FILE", whitelist)
    monkeypatch.setattr(lists, "_recompile", lambda: 0)

    rc = lists.add_whitelist("Example.COM")
    assert rc == 0

    assert whitelist.read_text(encoding="utf-8") == "example.com\n"
    assert (whitelist.stat().st_mode & 0o777) == 0o644
