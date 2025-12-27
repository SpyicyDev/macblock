from dataclasses import dataclass

import pytest

import macblock.daemon as daemon
from macblock.exec import RunResult
from macblock.state import State, load_state


@dataclass
class _ServiceInfo:
    name: str
    device: str | None = None


def test_seconds_until_resume_none_when_disabled(monkeypatch: pytest.MonkeyPatch):
    st = State(
        schema_version=2,
        enabled=False,
        resume_at_epoch=None,
        blocklist_source=None,
        dns_backup={},
        managed_services=[],
        resolver_domains=[],
    )
    assert daemon._seconds_until_resume(st) is None


def test_seconds_until_resume_counts_down(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(daemon.time, "time", lambda: 1000.0)
    st = State(
        schema_version=2,
        enabled=True,
        resume_at_epoch=1030,
        blocklist_source=None,
        dns_backup={},
        managed_services=[],
        resolver_domains=[],
    )
    assert daemon._seconds_until_resume(st) == 30.0


def test_update_upstreams_writes_defaults_and_per_domain(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    upstream_conf = tmp_path / "upstream.conf"
    monkeypatch.setattr(daemon, "VAR_DB_UPSTREAM_CONF", upstream_conf)
    monkeypatch.setattr(daemon, "_load_exclude_services", lambda: set())
    monkeypatch.setattr(
        daemon, "_collect_upstream_defaults", lambda _state, _exc: ["1.1.1.1"]
    )

    class _Resolvers:
        defaults = ["9.9.9.9"]
        per_domain = {"corp.example": ["10.0.0.1", "127.0.0.1"]}

    monkeypatch.setattr(daemon, "read_system_resolvers", lambda: _Resolvers())

    st = State(
        schema_version=2,
        enabled=False,
        resume_at_epoch=None,
        blocklist_source=None,
        dns_backup={},
        managed_services=[],
        resolver_domains=[],
    )

    changed = daemon._update_upstreams(st)
    assert changed is True

    text = upstream_conf.read_text(encoding="utf-8")
    assert "server=1.1.1.1\n" in text
    assert "server=/corp.example/10.0.0.1\n" in text
    assert "127.0.0.1" not in text


def test_apply_state_enables_blocking_and_persists_state(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    state_file = tmp_path / "state.json"
    upstream_conf = tmp_path / "upstream.conf"

    monkeypatch.setattr(daemon, "SYSTEM_STATE_FILE", state_file)
    monkeypatch.setattr(daemon, "VAR_DB_UPSTREAM_CONF", upstream_conf)

    monkeypatch.setattr(daemon.time, "time", lambda: 1000.0)

    monkeypatch.setattr(
        daemon,
        "compute_managed_services",
        lambda exclude=None: [_ServiceInfo("Wi-Fi", "en0")],
    )
    dns_by_service = {"Wi-Fi": ["8.8.8.8"]}

    def _get_dns(service: str):
        return dns_by_service.get(service, [])

    monkeypatch.setattr(daemon, "get_dns_servers", _get_dns)
    monkeypatch.setattr(daemon, "get_search_domains", lambda _svc: ["corp"])
    monkeypatch.setattr(daemon, "read_dhcp_nameservers", lambda _dev: ["1.1.1.1"])

    set_calls = []

    def _set_dns(service: str, servers):
        dns_by_service[service] = list(servers) if servers is not None else []
        set_calls.append((service, servers))
        return True

    monkeypatch.setattr(daemon, "set_dns_servers", _set_dns)

    monkeypatch.setattr(daemon, "_update_upstreams", lambda _state: False)
    monkeypatch.setattr(daemon, "_hup_dnsmasq", lambda: True)

    daemon.save_state_atomic(
        state_file,
        State(
            schema_version=2,
            enabled=True,
            resume_at_epoch=None,
            blocklist_source=None,
            dns_backup={},
            managed_services=[],
            resolver_domains=[],
        ),
    )

    ok, issues = daemon._apply_state()
    assert ok is True
    assert issues == []
    assert set_calls == [("Wi-Fi", ["127.0.0.1"])]

    st2 = load_state(state_file)
    assert st2.managed_services == ["Wi-Fi"]
    assert "Wi-Fi" in st2.dns_backup


def test_apply_state_paused_restores_dns(tmp_path, monkeypatch: pytest.MonkeyPatch):
    state_file = tmp_path / "state.json"
    upstream_conf = tmp_path / "upstream.conf"

    monkeypatch.setattr(daemon, "SYSTEM_STATE_FILE", state_file)
    monkeypatch.setattr(daemon, "VAR_DB_UPSTREAM_CONF", upstream_conf)
    monkeypatch.setattr(daemon.time, "time", lambda: 1000.0)

    monkeypatch.setattr(
        daemon,
        "compute_managed_services",
        lambda exclude=None: [_ServiceInfo("Wi-Fi", "en0")],
    )

    dns_by_service = {"Wi-Fi": ["127.0.0.1"]}

    def _get_dns(service: str):
        return dns_by_service.get(service, [])

    monkeypatch.setattr(daemon, "get_dns_servers", _get_dns)

    restore_calls = []

    def _set_dns(service: str, servers):
        dns_by_service[service] = list(servers) if servers is not None else []
        restore_calls.append((service, servers))
        return True

    def _set_search(service: str, search):
        restore_calls.append((service, search))
        return True

    monkeypatch.setattr(daemon, "set_dns_servers", _set_dns)
    monkeypatch.setattr(daemon, "set_search_domains", _set_search)
    monkeypatch.setattr(daemon, "_update_upstreams", lambda _state: False)
    monkeypatch.setattr(daemon, "_hup_dnsmasq", lambda: True)

    daemon.save_state_atomic(
        state_file,
        State(
            schema_version=2,
            enabled=True,
            resume_at_epoch=2000,
            blocklist_source=None,
            dns_backup={
                "Wi-Fi": {"dns": ["9.9.9.9"], "search": ["corp"], "dhcp": None}
            },
            managed_services=["Wi-Fi"],
            resolver_domains=[],
        ),
    )

    ok, issues = daemon._apply_state()
    assert ok is True
    assert issues == []
    assert ("Wi-Fi", ["9.9.9.9"]) in restore_calls
    assert ("Wi-Fi", ["corp"]) in restore_calls


class _FakeClock:
    def __init__(self):
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _mk_state(*, enabled: bool, resume_at_epoch: int | None) -> State:
    return State(
        schema_version=2,
        enabled=enabled,
        resume_at_epoch=resume_at_epoch,
        blocklist_source=None,
        dns_backup={},
        managed_services=[],
        resolver_domains=[],
    )


def test_should_wait_for_network_before_apply(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(daemon.time, "time", lambda: 1000.0)

    assert (
        daemon._should_wait_for_network_before_apply(
            _mk_state(enabled=False, resume_at_epoch=None)
        )
        is False
    )
    assert (
        daemon._should_wait_for_network_before_apply(
            _mk_state(enabled=True, resume_at_epoch=None)
        )
        is True
    )
    assert (
        daemon._should_wait_for_network_before_apply(
            _mk_state(enabled=True, resume_at_epoch=2000)
        )
        is False
    )
    assert (
        daemon._should_wait_for_network_before_apply(
            _mk_state(enabled=True, resume_at_epoch=900)
        )
        is True
    )


def test_wait_for_network_ready_waits_until_route_and_ip(
    monkeypatch: pytest.MonkeyPatch,
):
    clock = _FakeClock()
    monkeypatch.setattr(daemon.time, "time", clock.time)
    monkeypatch.setattr(daemon.time, "sleep", clock.sleep)
    monkeypatch.setattr(daemon, "_shutdown_requested", False)
    monkeypatch.setattr(daemon, "_trigger_apply", False)

    def _run(cmd: list[str], *, timeout: float | None = 10.0) -> RunResult:
        if cmd == ["/sbin/route", "-n", "get", "default"]:
            if clock.now < 1.0:
                return RunResult(returncode=1, stdout="", stderr="not in table")
            return RunResult(returncode=0, stdout="interface: en0\n", stderr="")

        if cmd == ["/usr/sbin/ipconfig", "getifaddr", "en0"]:
            if clock.now < 1.0:
                return RunResult(returncode=1, stdout="", stderr="")
            return RunResult(returncode=0, stdout="192.168.0.10\n", stderr="")

        raise AssertionError(f"unexpected cmd: {cmd}")

    monkeypatch.setattr(daemon, "run", _run)

    ok = daemon._wait_for_network_ready(15.0)
    assert ok is True
    assert clock.now >= 1.0


def test_wait_for_network_ready_times_out(monkeypatch: pytest.MonkeyPatch):
    clock = _FakeClock()
    monkeypatch.setattr(daemon.time, "time", clock.time)
    monkeypatch.setattr(daemon.time, "sleep", clock.sleep)
    monkeypatch.setattr(daemon, "_shutdown_requested", False)
    monkeypatch.setattr(daemon, "_trigger_apply", False)

    def _run(cmd: list[str], *, timeout: float | None = 10.0) -> RunResult:
        return RunResult(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(daemon, "run", _run)

    ok = daemon._wait_for_network_ready(15.0)
    assert ok is False
    assert clock.now >= 15.0
