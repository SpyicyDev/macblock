from pathlib import Path

import pytest

import macblock.blocklists as blocklists
from macblock.blocklists import compile_blocklist
from macblock.errors import MacblockError
from macblock.state import State, load_state, save_state_atomic


def test_compile_applies_allow_and_deny(tmp_path: Path):
    raw = tmp_path / "raw"
    allow = tmp_path / "allow"
    deny = tmp_path / "deny"
    out = tmp_path / "out"

    raw.write_text("0.0.0.0 ads.example\n0.0.0.0 tracker.example\n", encoding="utf-8")
    allow.write_text("invalid@@\nads.example\n", encoding="utf-8")
    deny.write_text("extra.example\ninvalid@@\n", encoding="utf-8")

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

    def _fake_download(url: str, *, expected_sha256: str | None = None) -> str:
        return "0.0.0.0 ads.example\n"

    calls = {"save": 0, "reload": 0, "write": 0}

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

    with pytest.raises(MacblockError, match=r"too small"):
        blocklists.update_blocklist()

    assert calls == {"save": 0, "reload": 0, "write": 0}

    out = capsys.readouterr().out
    assert "Blocklist updated" not in out


def test_update_blocklist_rejects_html_download(
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

    def _fake_download(url: str, *, expected_sha256: str | None = None) -> str:
        return "<!doctype html><html>nope</html>"

    calls = {"save": 0, "reload": 0, "write": 0}

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

    with pytest.raises(MacblockError, match=r"looks like HTML"):
        blocklists.update_blocklist()

    assert calls == {"save": 0, "reload": 0, "write": 0}

    out = capsys.readouterr().out
    assert "Blocklist updated" not in out


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


@pytest.mark.parametrize("payload", ["", "\n", " \n\t"])
def test_update_blocklist_rejects_empty_download_does_not_drift(
    payload: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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
        return payload

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

    with pytest.raises(MacblockError, match=r"downloaded blocklist is empty"):
        blocklists.update_blocklist()

    assert calls == {"save": 0, "reload": 0, "write": 0}

    out = capsys.readouterr().out
    assert "Blocklist updated" not in out


def test_reload_dnsmasq_raises_when_hup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_file = tmp_path / "dnsmasq.pid"
    pid_file.write_text("123\n", encoding="utf-8")

    monkeypatch.setattr(blocklists, "VAR_DB_DNSMASQ_PID", pid_file)
    monkeypatch.setattr(blocklists, "service_exists", lambda _label: False)

    from macblock.exec import RunResult

    monkeypatch.setattr(blocklists, "run", lambda _cmd: RunResult(1, "", "nope"))

    with pytest.raises(MacblockError, match=r"failed to reload dnsmasq"):
        blocklists.reload_dnsmasq()


def test_update_blocklist_rolls_back_on_reload_failure_existing_files(
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

    old_raw = "old raw\n"
    old_conf = "old conf\n"
    raw_file.write_text(old_raw, encoding="utf-8")
    out_file.write_text(old_conf, encoding="utf-8")

    save_state_atomic(
        state_file,
        State(
            schema_version=2,
            enabled=False,
            resume_at_epoch=None,
            blocklist_source="old",
            dns_backup={},
            managed_services=[],
            resolver_domains=[],
        ),
    )

    prev_state_text = state_file.read_text(encoding="utf-8")

    domains = [f"d{i}.example" for i in range(1000)]
    payload = "\n".join([f"0.0.0.0 {d}" for d in domains]) + "\n"

    monkeypatch.setattr(blocklists, "_download", lambda *_a, **_k: payload)
    monkeypatch.setattr(
        blocklists,
        "reload_dnsmasq",
        lambda: (_ for _ in ()).throw(MacblockError("reload failed")),
    )

    with pytest.raises(MacblockError, match=r"failed to reload dnsmasq"):
        blocklists.update_blocklist(source="https://example.invalid/new")

    assert raw_file.read_text(encoding="utf-8") == old_raw
    assert out_file.read_text(encoding="utf-8") == old_conf
    assert state_file.read_text(encoding="utf-8") == prev_state_text
    assert load_state(state_file).blocklist_source == "old"

    out = capsys.readouterr().out
    assert "Blocklist updated" not in out


def test_update_blocklist_rolls_back_on_reload_failure_when_files_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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

    domains = [f"d{i}.example" for i in range(1000)]
    payload = "\n".join([f"0.0.0.0 {d}" for d in domains]) + "\n"

    monkeypatch.setattr(blocklists, "_download", lambda *_a, **_k: payload)
    monkeypatch.setattr(
        blocklists,
        "reload_dnsmasq",
        lambda: (_ for _ in ()).throw(MacblockError("reload failed")),
    )

    with pytest.raises(MacblockError, match=r"failed to reload dnsmasq"):
        blocklists.update_blocklist()

    assert not raw_file.exists()
    assert not out_file.exists()
    assert not state_file.exists()
