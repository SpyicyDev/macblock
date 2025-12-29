from pathlib import Path

import pytest

import macblock.blocklists as blocklists
from macblock.blocklists import compile_blocklist
from macblock.errors import MacblockError


def test_compile_applies_allow_and_deny(tmp_path: Path):
    raw = tmp_path / "raw"
    allow = tmp_path / "allow"
    deny = tmp_path / "deny"
    out = tmp_path / "out"

    raw.write_text("0.0.0.0 ads.example\n0.0.0.0 tracker.example\n", encoding="utf-8")
    allow.write_text("ads.example\n", encoding="utf-8")
    deny.write_text("extra.example\n", encoding="utf-8")

    count = compile_blocklist(raw, allow, deny, out)
    assert count == 2

    text = out.read_text(encoding="utf-8")
    assert "server=/tracker.example/\n" in text
    assert "server=/extra.example/\n" in text
    assert "ads.example" not in text


def test_update_blocklist_refuses_small_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    state_file = tmp_path / "state.json"
    raw_file = tmp_path / "blocklist.raw"
    out_file = tmp_path / "blocklist.conf"
    allow_file = tmp_path / "whitelist.txt"
    deny_file = tmp_path / "blacklist.txt"

    monkeypatch.setattr(blocklists, "SYSTEM_STATE_FILE", state_file)
    monkeypatch.setattr(blocklists, "SYSTEM_RAW_BLOCKLIST_FILE", raw_file)
    monkeypatch.setattr(blocklists, "SYSTEM_BLOCKLIST_FILE", out_file)
    monkeypatch.setattr(blocklists, "SYSTEM_WHITELIST_FILE", allow_file)
    monkeypatch.setattr(blocklists, "SYSTEM_BLACKLIST_FILE", deny_file)

    monkeypatch.setattr(
        blocklists, "DEFAULT_BLOCKLIST_SOURCE", "https://example.invalid/list"
    )

    calls = {"save": 0, "reload": 0, "write": 0}

    def _fake_download(url: str, *, expected_sha256: str | None = None) -> str:
        return "0.0.0.0 ads.example\n0.0.0.0 tracker.example\n"

    def _fake_atomic_write_text(path: Path, text: str, mode: int | None = None) -> None:
        calls["write"] += 1

    def _fake_save_state_atomic(path: Path, state) -> None:
        calls["save"] += 1

    def _fake_reload_dnsmasq() -> None:
        calls["reload"] += 1

    monkeypatch.setattr(blocklists, "_download", _fake_download)
    monkeypatch.setattr(blocklists, "atomic_write_text", _fake_atomic_write_text)
    monkeypatch.setattr(blocklists, "save_state_atomic", _fake_save_state_atomic)
    monkeypatch.setattr(blocklists, "reload_dnsmasq", _fake_reload_dnsmasq)

    with pytest.raises(MacblockError):
        blocklists.update_blocklist()

    assert calls == {"save": 0, "reload": 0, "write": 0}

    out = capsys.readouterr().out
    assert "Blocklist updated" not in out


def test_update_blocklist_rejects_html_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(blocklists, "SYSTEM_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(
        blocklists, "DEFAULT_BLOCKLIST_SOURCE", "https://example.invalid/list"
    )

    calls = {"save": 0, "reload": 0, "write": 0}

    def _fake_download(url: str, *, expected_sha256: str | None = None) -> str:
        return "<html><body>nope</body></html>"

    def _fake_atomic_write_text(path: Path, text: str, mode: int | None = None) -> None:
        calls["write"] += 1

    def _fake_save_state_atomic(path: Path, state) -> None:
        calls["save"] += 1

    def _fake_reload_dnsmasq() -> None:
        calls["reload"] += 1

    monkeypatch.setattr(blocklists, "_download", _fake_download)
    monkeypatch.setattr(blocklists, "atomic_write_text", _fake_atomic_write_text)
    monkeypatch.setattr(blocklists, "save_state_atomic", _fake_save_state_atomic)
    monkeypatch.setattr(blocklists, "reload_dnsmasq", _fake_reload_dnsmasq)

    with pytest.raises(MacblockError):
        blocklists.update_blocklist()

    assert calls == {"save": 0, "reload": 0, "write": 0}


def test_update_blocklist_does_not_drift_state_on_sha_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(blocklists, "SYSTEM_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(
        blocklists, "DEFAULT_BLOCKLIST_SOURCE", "https://example.invalid/list"
    )

    calls = {"save": 0, "reload": 0, "write": 0}

    class _FakeResponse:
        def __init__(self, payload: bytes):
            self._payload = payload
            self._sent = False

        def read(self, _n: int) -> bytes:
            if self._sent:
                return b""
            self._sent = True
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(_req, timeout: float = 30.0):
        return _FakeResponse(b"0.0.0.0 ads.example\n")

    def _fake_atomic_write_text(path: Path, text: str, mode: int | None = None) -> None:
        calls["write"] += 1

    def _fake_save_state_atomic(path: Path, state) -> None:
        calls["save"] += 1

    def _fake_reload_dnsmasq() -> None:
        calls["reload"] += 1

    monkeypatch.setattr(blocklists.urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(blocklists, "atomic_write_text", _fake_atomic_write_text)
    monkeypatch.setattr(blocklists, "save_state_atomic", _fake_save_state_atomic)
    monkeypatch.setattr(blocklists, "reload_dnsmasq", _fake_reload_dnsmasq)

    with pytest.raises(MacblockError):
        blocklists.update_blocklist(sha256="0" * 64)

    assert calls == {"save": 0, "reload": 0, "write": 0}
