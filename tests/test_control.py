from macblock.control import _atomic_write


def test_atomic_write_pins_mode(tmp_path) -> None:
    path = tmp_path / "config.txt"
    _atomic_write(path, "hello\n")
    assert path.read_text(encoding="utf-8") == "hello\n"
    assert (path.stat().st_mode & 0o777) == 0o644
