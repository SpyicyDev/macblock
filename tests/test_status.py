import pytest

import macblock.status as status
from macblock.errors import MacblockError
from macblock.exec import RunResult


def test_show_status_reports_corrupt_state_and_returns_1(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(status, "SYSTEM_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(status, "SYSTEM_BLOCKLIST_FILE", tmp_path / "blocklist.conf")
    monkeypatch.setattr(status, "VAR_DB_DNSMASQ_PID", tmp_path / "dnsmasq.pid")
    monkeypatch.setattr(status, "VAR_DB_DAEMON_PID", tmp_path / "daemon.pid")
    monkeypatch.setattr(status, "VAR_DB_DAEMON_LAST_APPLY", tmp_path / "daemon.last")
    monkeypatch.setattr(status, "VAR_DB_UPSTREAM_CONF", tmp_path / "upstream.conf")
    monkeypatch.setattr(
        status, "SYSTEM_UPSTREAM_FALLBACKS_FILE", tmp_path / "fallbacks"
    )
    monkeypatch.setattr(status, "LAUNCHD_DIR", tmp_path / "launchd")
    monkeypatch.setattr(
        status, "LAUNCHD_DNSMASQ_PLIST", tmp_path / "launchd" / "dnsmasq.plist"
    )

    def _load_state(_path):
        raise MacblockError("state file is corrupt: state.json")

    monkeypatch.setattr(status, "load_state", _load_state)
    monkeypatch.setattr(status, "run", lambda _cmd: RunResult(1, "", ""))

    rc = status.show_status()
    assert rc == 1

    out = capsys.readouterr().out
    assert "state.json" in out
    assert "state file is corrupt" in out
    assert "Services" in out
