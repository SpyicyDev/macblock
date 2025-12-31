from pathlib import Path

import pytest

from macblock.errors import MacblockError
from macblock.state import State, load_state, save_state_atomic


def test_save_state_atomic_pins_mode(tmp_path) -> None:
    path = tmp_path / "state.json"
    save_state_atomic(
        path,
        State(
            schema_version=2,
            enabled=False,
            resume_at_epoch=None,
            blocklist_source=None,
            dns_backup={},
            managed_services=[],
        ),
    )

    assert (path.stat().st_mode & 0o777) == 0o644


def test_save_state_atomic_writes_json(tmp_path) -> None:
    path = tmp_path / "state.json"
    save_state_atomic(
        path,
        State(
            schema_version=2,
            enabled=True,
            resume_at_epoch=123,
            blocklist_source="src",
            dns_backup={},
            managed_services=["Wi-Fi"],
        ),
    )

    text = path.read_text(encoding="utf-8")
    assert '"enabled": true' in text
    assert '"resume_at_epoch": 123' in text
    assert text.endswith("\n")


def test_load_state_raises_on_invalid_json(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{ invalid", encoding="utf-8")

    with pytest.raises(MacblockError, match=r"corrupt"):
        load_state(path)


def test_load_state_raises_on_non_object_json(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(MacblockError, match=r"JSON object"):
        load_state(path)


def test_load_state_raises_on_invalid_schema_version(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"schema_version": "two"}', encoding="utf-8")

    with pytest.raises(MacblockError, match=r"schema_version"):
        load_state(path)


def test_load_state_returns_default_when_missing(tmp_path) -> None:
    st = load_state(tmp_path / "missing.json")
    assert st.enabled is False
    assert st.resume_at_epoch is None


def test_load_state_ignores_legacy_resolver_domains(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        '{"schema_version": 2, "enabled": false, "resolver_domains": ["x.example"]}',
        encoding="utf-8",
    )

    st = load_state(path)
    assert st.enabled is False
    assert hasattr(st, "resolver_domains") is False


def test_load_state_raises_on_read_oserror(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    path.write_text("{}", encoding="utf-8")

    original_read_text = Path.read_text

    def _read_text(self: Path, *args, **kwargs):
        if self == path:
            raise OSError("simulated read failure")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _read_text)

    with pytest.raises(
        MacblockError,
        match=r"failed to read state file: .*state\.json.*delete it to reset to defaults",
    ):
        load_state(path)


def test_load_state_raises_on_read_unicode_decode_error(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    path.write_text("{}", encoding="utf-8")

    original_read_text = Path.read_text

    def _read_text(self: Path, *args, **kwargs):
        if self == path:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "simulated decode failure")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _read_text)

    with pytest.raises(
        MacblockError,
        match=r"failed to read state file: .*state\.json.*delete it to reset to defaults",
    ):
        load_state(path)
