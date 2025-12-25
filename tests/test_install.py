import errno
from dataclasses import dataclass

import pytest

import macblock.install as install
from macblock.errors import MacblockError


class _DummySpinner:
    def __init__(self, _msg: str):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def fail(self, _msg: str):
        pass

    def succeed(self, _msg: str):
        pass

    def warn(self, _msg: str):
        pass


@dataclass
class _RunResult:
    returncode: int
    stdout: str = ""


def test_find_dnsmasq_bin_raises_when_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(install, "_check_dnsmasq_installed", lambda: (False, None))
    with pytest.raises(MacblockError, match="dnsmasq not found"):
        install._find_dnsmasq_bin()


def test_check_port_available_reports_blocker_from_lsof(
    monkeypatch: pytest.MonkeyPatch,
):
    class _FakeSocket:
        def settimeout(self, _v: float):
            pass

        def bind(self, _addr):
            raise OSError(errno.EADDRINUSE, "Address already in use")

        def close(self):
            pass

    monkeypatch.setattr(install.socket, "socket", lambda *_a, **_k: _FakeSocket())
    monkeypatch.setattr(
        install,
        "run",
        lambda _cmd: _RunResult(
            returncode=0,
            stdout="COMMAND PID\ndnsmasq 123\n",
        ),
    )

    ok, blocker = install._check_port_available("127.0.0.1", 53)
    assert ok is False
    assert blocker == "dnsmasq"


def test_run_preflight_checks_raises_when_dnsmasq_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(install, "Spinner", _DummySpinner)
    monkeypatch.setattr(install, "_check_dnsmasq_installed", lambda: (False, None))

    with pytest.raises(MacblockError, match="dnsmasq is not installed"):
        install._run_preflight_checks(force=False)


def test_restore_dns_from_state_calls_restore(monkeypatch: pytest.MonkeyPatch):
    calls = []

    def _restore(service: str, backup):
        calls.append((service, backup.dns_servers, backup.search_domains))

    monkeypatch.setattr(install, "restore_from_backup", _restore)

    st = install.State(
        schema_version=2,
        enabled=False,
        resume_at_epoch=None,
        blocklist_source=None,
        dns_backup={"Wi-Fi": {"dns": ["8.8.8.8"], "search": ["corp"], "dhcp": None}},
        managed_services=["Wi-Fi"],
        resolver_domains=[],
    )

    install._restore_dns_from_state(st)

    assert calls == [("Wi-Fi", ["8.8.8.8"], ["corp"])]


def test_remove_any_macblock_resolvers_removes_marked_files(tmp_path):
    resolver_dir = tmp_path / "resolver"
    resolver_dir.mkdir()

    keep = resolver_dir / "keep"
    keep.write_text("nameserver 8.8.8.8\n", encoding="utf-8")

    rm = resolver_dir / "rm"
    rm.write_text("# macblock\nnameserver 127.0.0.1\n", encoding="utf-8")

    install.SYSTEM_RESOLVER_DIR = resolver_dir

    install._remove_any_macblock_resolvers()

    assert keep.exists()
    assert not rm.exists()
