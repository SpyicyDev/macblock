from macblock.state import State, save_state_atomic


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
            resolver_domains=[],
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
            resolver_domains=[],
        ),
    )

    text = path.read_text(encoding="utf-8")
    assert '"enabled": true' in text
    assert '"resume_at_epoch": 123' in text
    assert text.endswith("\n")
