import pytest

import macblock.doctor as doctor
from macblock.errors import MacblockError
from macblock.exec import RunResult


def test_doctor_continues_when_state_is_corrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(doctor, "SYSTEM_VERSION_FILE", tmp_path / "version")
    monkeypatch.setattr(doctor, "SYSTEM_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(doctor, "SYSTEM_DNSMASQ_CONF", tmp_path / "dnsmasq.conf")
    monkeypatch.setattr(doctor, "SYSTEM_RAW_BLOCKLIST_FILE", tmp_path / "blocklist.raw")
    monkeypatch.setattr(doctor, "SYSTEM_BLOCKLIST_FILE", tmp_path / "blocklist.conf")
    monkeypatch.setattr(doctor, "VAR_DB_UPSTREAM_CONF", tmp_path / "upstream.conf")
    monkeypatch.setattr(
        doctor, "SYSTEM_UPSTREAM_FALLBACKS_FILE", tmp_path / "fallbacks"
    )
    monkeypatch.setattr(doctor, "SYSTEM_LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(doctor, "LAUNCHD_DIR", tmp_path / "launchd")
    monkeypatch.setattr(
        doctor, "LAUNCHD_DNSMASQ_PLIST", tmp_path / "launchd" / "dnsmasq.plist"
    )
    monkeypatch.setattr(doctor, "VAR_DB_DNSMASQ_PID", tmp_path / "dnsmasq.pid")
    monkeypatch.setattr(doctor, "VAR_DB_DAEMON_PID", tmp_path / "daemon.pid")
    monkeypatch.setattr(doctor, "VAR_DB_DAEMON_READY", tmp_path / "daemon.ready")
    monkeypatch.setattr(doctor, "VAR_DB_DAEMON_LAST_APPLY", tmp_path / "daemon.last")

    monkeypatch.setattr(doctor, "_tcp_connect_ok", lambda *_a, **_k: False)
    monkeypatch.setattr(doctor, "run", lambda _cmd: RunResult(1, "", ""))

    def _load_state(_path):
        raise MacblockError("state file is corrupt: state.json")

    monkeypatch.setattr(doctor, "load_state", _load_state)

    rc = doctor.run_diagnostics()
    assert rc == 1

    out = capsys.readouterr().out
    assert "DNS State" in out
    assert "state file is corrupt" in out
    assert "Issues" in out
