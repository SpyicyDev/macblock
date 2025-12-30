import errno
from dataclasses import dataclass
from pathlib import Path

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


def test_do_uninstall_force_continues_when_unlink_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(install, "Spinner", _DummySpinner)
    monkeypatch.setattr(install, "_restore_dns_from_state", lambda _st: None)
    monkeypatch.setattr(install, "_remove_any_macblock_resolvers", lambda: None)
    monkeypatch.setattr(install, "bootout_system", lambda *_a, **_k: None)
    monkeypatch.setattr(install, "service_exists", lambda _label: False)
    monkeypatch.setattr(install, "delete_system_user", lambda _user: None)
    monkeypatch.setattr(install, "result_success", lambda _msg: None)

    st = install.State(
        schema_version=2,
        enabled=False,
        resume_at_epoch=None,
        blocklist_source=None,
        dns_backup={},
        managed_services=[],
        resolver_domains=[],
    )
    monkeypatch.setattr(install, "load_state", lambda _p: st)

    warnings: list[str] = []
    monkeypatch.setattr(install, "step_warn", lambda msg: warnings.append(msg))

    launchd_dir = tmp_path / "launchd"
    launchd_dir.mkdir()
    failing = launchd_dir / "dnsmasq.plist"
    failing.write_text("test\n", encoding="utf-8")

    monkeypatch.setattr(install, "LAUNCHD_DIR", launchd_dir)
    monkeypatch.setattr(install, "LAUNCHD_DNSMASQ_PLIST", failing)
    monkeypatch.setattr(install, "LAUNCHD_DAEMON_PLIST", launchd_dir / "daemon.plist")
    monkeypatch.setattr(
        install, "LAUNCHD_UPSTREAMS_PLIST", launchd_dir / "upstreams.plist"
    )
    monkeypatch.setattr(install, "LAUNCHD_STATE_PLIST", launchd_dir / "state.plist")

    monkeypatch.setattr(install, "SYSTEM_SUPPORT_DIR", tmp_path / "support")
    monkeypatch.setattr(install, "SYSTEM_CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(install, "SYSTEM_LOG_DIR", tmp_path / "logs")

    monkeypatch.setattr(install, "VAR_DB_DIR", tmp_path / "var-db")
    monkeypatch.setattr(install, "VAR_DB_DNSMASQ_DIR", tmp_path / "var-db-dnsmasq")
    monkeypatch.setattr(install, "VAR_DB_UPSTREAM_CONF", tmp_path / "upstream.conf")
    monkeypatch.setattr(install, "VAR_DB_DNSMASQ_PID", tmp_path / "dnsmasq.pid")
    monkeypatch.setattr(install, "VAR_DB_DAEMON_PID", tmp_path / "daemon.pid")
    monkeypatch.setattr(install, "VAR_DB_DAEMON_LAST_APPLY", tmp_path / "daemon.last")

    monkeypatch.setattr(install, "SYSTEM_DNSMASQ_CONF", tmp_path / "dnsmasq.conf")
    monkeypatch.setattr(
        install, "SYSTEM_RAW_BLOCKLIST_FILE", tmp_path / "blocklist.raw"
    )
    monkeypatch.setattr(install, "SYSTEM_BLOCKLIST_FILE", tmp_path / "blocklist.conf")
    monkeypatch.setattr(install, "SYSTEM_WHITELIST_FILE", tmp_path / "whitelist.txt")
    monkeypatch.setattr(install, "SYSTEM_BLACKLIST_FILE", tmp_path / "blacklist.txt")
    monkeypatch.setattr(install, "SYSTEM_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(install, "SYSTEM_VERSION_FILE", tmp_path / "version")
    monkeypatch.setattr(
        install, "SYSTEM_DNS_EXCLUDE_SERVICES_FILE", tmp_path / "exclude"
    )
    monkeypatch.setattr(
        install, "SYSTEM_UPSTREAM_FALLBACKS_FILE", tmp_path / "fallbacks"
    )

    original_unlink = Path.unlink

    def _unlink(self: Path, *args, **kwargs):
        if self == failing:
            raise OSError("nope")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _unlink)

    rc = install.do_uninstall(force=True)
    assert rc == 0
    assert any("Uninstall incomplete:" in w for w in warnings)
    assert any(str(failing) in w for w in warnings)


def test_do_uninstall_non_force_raises_on_unlink_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(install, "Spinner", _DummySpinner)
    monkeypatch.setattr(install, "_restore_dns_from_state", lambda _st: None)
    monkeypatch.setattr(install, "_remove_any_macblock_resolvers", lambda: None)
    monkeypatch.setattr(install, "bootout_system", lambda *_a, **_k: None)
    monkeypatch.setattr(install, "service_exists", lambda _label: False)
    monkeypatch.setattr(install, "result_success", lambda _msg: None)

    st = install.State(
        schema_version=2,
        enabled=False,
        resume_at_epoch=None,
        blocklist_source=None,
        dns_backup={},
        managed_services=[],
        resolver_domains=[],
    )
    monkeypatch.setattr(install, "load_state", lambda _p: st)

    launchd_dir = tmp_path / "launchd"
    launchd_dir.mkdir()
    failing = launchd_dir / "dnsmasq.plist"
    failing.write_text("test\n", encoding="utf-8")

    monkeypatch.setattr(install, "LAUNCHD_DIR", launchd_dir)
    monkeypatch.setattr(install, "LAUNCHD_DNSMASQ_PLIST", failing)
    monkeypatch.setattr(install, "LAUNCHD_DAEMON_PLIST", launchd_dir / "daemon.plist")
    monkeypatch.setattr(
        install, "LAUNCHD_UPSTREAMS_PLIST", launchd_dir / "upstreams.plist"
    )
    monkeypatch.setattr(install, "LAUNCHD_STATE_PLIST", launchd_dir / "state.plist")

    monkeypatch.setattr(install, "SYSTEM_SUPPORT_DIR", tmp_path / "support")
    monkeypatch.setattr(install, "SYSTEM_CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(install, "SYSTEM_LOG_DIR", tmp_path / "logs")

    monkeypatch.setattr(install, "VAR_DB_DIR", tmp_path / "var-db")
    monkeypatch.setattr(install, "VAR_DB_DNSMASQ_DIR", tmp_path / "var-db-dnsmasq")
    monkeypatch.setattr(install, "VAR_DB_UPSTREAM_CONF", tmp_path / "upstream.conf")
    monkeypatch.setattr(install, "VAR_DB_DNSMASQ_PID", tmp_path / "dnsmasq.pid")
    monkeypatch.setattr(install, "VAR_DB_DAEMON_PID", tmp_path / "daemon.pid")
    monkeypatch.setattr(install, "VAR_DB_DAEMON_LAST_APPLY", tmp_path / "daemon.last")

    monkeypatch.setattr(install, "SYSTEM_DNSMASQ_CONF", tmp_path / "dnsmasq.conf")
    monkeypatch.setattr(
        install, "SYSTEM_RAW_BLOCKLIST_FILE", tmp_path / "blocklist.raw"
    )
    monkeypatch.setattr(install, "SYSTEM_BLOCKLIST_FILE", tmp_path / "blocklist.conf")
    monkeypatch.setattr(install, "SYSTEM_WHITELIST_FILE", tmp_path / "whitelist.txt")
    monkeypatch.setattr(install, "SYSTEM_BLACKLIST_FILE", tmp_path / "blacklist.txt")
    monkeypatch.setattr(install, "SYSTEM_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(install, "SYSTEM_VERSION_FILE", tmp_path / "version")
    monkeypatch.setattr(
        install, "SYSTEM_DNS_EXCLUDE_SERVICES_FILE", tmp_path / "exclude"
    )
    monkeypatch.setattr(
        install, "SYSTEM_UPSTREAM_FALLBACKS_FILE", tmp_path / "fallbacks"
    )

    original_unlink = Path.unlink

    def _unlink(self: Path, *args, **kwargs):
        if self == failing:
            raise OSError("nope")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _unlink)

    with pytest.raises(MacblockError, match="failed to remove"):
        install.do_uninstall(force=False)


def test_do_uninstall_force_reports_dir_leftovers_when_rmdir_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(install, "Spinner", _DummySpinner)
    monkeypatch.setattr(install, "_restore_dns_from_state", lambda _st: None)
    monkeypatch.setattr(install, "_remove_any_macblock_resolvers", lambda: None)
    monkeypatch.setattr(install, "bootout_system", lambda *_a, **_k: None)
    monkeypatch.setattr(install, "service_exists", lambda _label: False)
    monkeypatch.setattr(install, "delete_system_user", lambda _user: None)
    monkeypatch.setattr(install, "result_success", lambda _msg: None)

    st = install.State(
        schema_version=2,
        enabled=False,
        resume_at_epoch=None,
        blocklist_source=None,
        dns_backup={},
        managed_services=[],
        resolver_domains=[],
    )
    monkeypatch.setattr(install, "load_state", lambda _p: st)

    warnings: list[str] = []
    monkeypatch.setattr(install, "step_warn", lambda msg: warnings.append(msg))

    launchd_dir = tmp_path / "launchd"
    launchd_dir.mkdir()
    monkeypatch.setattr(install, "LAUNCHD_DIR", launchd_dir)
    monkeypatch.setattr(install, "LAUNCHD_DNSMASQ_PLIST", launchd_dir / "dnsmasq.plist")
    monkeypatch.setattr(install, "LAUNCHD_DAEMON_PLIST", launchd_dir / "daemon.plist")
    monkeypatch.setattr(
        install, "LAUNCHD_UPSTREAMS_PLIST", launchd_dir / "upstreams.plist"
    )
    monkeypatch.setattr(install, "LAUNCHD_STATE_PLIST", launchd_dir / "state.plist")

    support_dir = tmp_path / "support"
    support_dir.mkdir()
    (support_dir / "extra").write_text("x\n", encoding="utf-8")

    monkeypatch.setattr(install, "SYSTEM_SUPPORT_DIR", support_dir)
    monkeypatch.setattr(install, "SYSTEM_CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(install, "SYSTEM_LOG_DIR", tmp_path / "logs")

    monkeypatch.setattr(install, "VAR_DB_DIR", tmp_path / "var-db")
    monkeypatch.setattr(install, "VAR_DB_DNSMASQ_DIR", tmp_path / "var-db-dnsmasq")
    monkeypatch.setattr(install, "VAR_DB_UPSTREAM_CONF", tmp_path / "upstream.conf")
    monkeypatch.setattr(install, "VAR_DB_DNSMASQ_PID", tmp_path / "dnsmasq.pid")
    monkeypatch.setattr(install, "VAR_DB_DAEMON_PID", tmp_path / "daemon.pid")
    monkeypatch.setattr(install, "VAR_DB_DAEMON_LAST_APPLY", tmp_path / "daemon.last")

    monkeypatch.setattr(install, "SYSTEM_DNSMASQ_CONF", tmp_path / "dnsmasq.conf")
    monkeypatch.setattr(
        install, "SYSTEM_RAW_BLOCKLIST_FILE", tmp_path / "blocklist.raw"
    )
    monkeypatch.setattr(install, "SYSTEM_BLOCKLIST_FILE", tmp_path / "blocklist.conf")
    monkeypatch.setattr(install, "SYSTEM_WHITELIST_FILE", tmp_path / "whitelist.txt")
    monkeypatch.setattr(install, "SYSTEM_BLACKLIST_FILE", tmp_path / "blacklist.txt")
    monkeypatch.setattr(install, "SYSTEM_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(install, "SYSTEM_VERSION_FILE", tmp_path / "version")
    monkeypatch.setattr(
        install, "SYSTEM_DNS_EXCLUDE_SERVICES_FILE", tmp_path / "exclude"
    )
    monkeypatch.setattr(
        install, "SYSTEM_UPSTREAM_FALLBACKS_FILE", tmp_path / "fallbacks"
    )

    rc = install.do_uninstall(force=True)
    assert rc == 0
    assert any("Uninstall incomplete:" in w for w in warnings)
    assert any(str(support_dir) in w for w in warnings)


def test_do_uninstall_non_force_raises_on_rmdir_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(install, "Spinner", _DummySpinner)
    monkeypatch.setattr(install, "_restore_dns_from_state", lambda _st: None)
    monkeypatch.setattr(install, "_remove_any_macblock_resolvers", lambda: None)
    monkeypatch.setattr(install, "bootout_system", lambda *_a, **_k: None)
    monkeypatch.setattr(install, "service_exists", lambda _label: False)
    monkeypatch.setattr(install, "result_success", lambda _msg: None)

    st = install.State(
        schema_version=2,
        enabled=False,
        resume_at_epoch=None,
        blocklist_source=None,
        dns_backup={},
        managed_services=[],
        resolver_domains=[],
    )
    monkeypatch.setattr(install, "load_state", lambda _p: st)

    launchd_dir = tmp_path / "launchd"
    launchd_dir.mkdir()
    monkeypatch.setattr(install, "LAUNCHD_DIR", launchd_dir)
    monkeypatch.setattr(install, "LAUNCHD_DNSMASQ_PLIST", launchd_dir / "dnsmasq.plist")
    monkeypatch.setattr(install, "LAUNCHD_DAEMON_PLIST", launchd_dir / "daemon.plist")
    monkeypatch.setattr(
        install, "LAUNCHD_UPSTREAMS_PLIST", launchd_dir / "upstreams.plist"
    )
    monkeypatch.setattr(install, "LAUNCHD_STATE_PLIST", launchd_dir / "state.plist")

    support_dir = tmp_path / "support"
    support_dir.mkdir()
    (support_dir / "extra").write_text("x\n", encoding="utf-8")

    monkeypatch.setattr(install, "SYSTEM_SUPPORT_DIR", support_dir)
    monkeypatch.setattr(install, "SYSTEM_CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(install, "SYSTEM_LOG_DIR", tmp_path / "logs")

    monkeypatch.setattr(install, "VAR_DB_DIR", tmp_path / "var-db")
    monkeypatch.setattr(install, "VAR_DB_DNSMASQ_DIR", tmp_path / "var-db-dnsmasq")
    monkeypatch.setattr(install, "VAR_DB_UPSTREAM_CONF", tmp_path / "upstream.conf")
    monkeypatch.setattr(install, "VAR_DB_DNSMASQ_PID", tmp_path / "dnsmasq.pid")
    monkeypatch.setattr(install, "VAR_DB_DAEMON_PID", tmp_path / "daemon.pid")
    monkeypatch.setattr(install, "VAR_DB_DAEMON_LAST_APPLY", tmp_path / "daemon.last")

    monkeypatch.setattr(install, "SYSTEM_DNSMASQ_CONF", tmp_path / "dnsmasq.conf")
    monkeypatch.setattr(
        install, "SYSTEM_RAW_BLOCKLIST_FILE", tmp_path / "blocklist.raw"
    )
    monkeypatch.setattr(install, "SYSTEM_BLOCKLIST_FILE", tmp_path / "blocklist.conf")
    monkeypatch.setattr(install, "SYSTEM_WHITELIST_FILE", tmp_path / "whitelist.txt")
    monkeypatch.setattr(install, "SYSTEM_BLACKLIST_FILE", tmp_path / "blacklist.txt")
    monkeypatch.setattr(install, "SYSTEM_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(install, "SYSTEM_VERSION_FILE", tmp_path / "version")
    monkeypatch.setattr(
        install, "SYSTEM_DNS_EXCLUDE_SERVICES_FILE", tmp_path / "exclude"
    )
    monkeypatch.setattr(
        install, "SYSTEM_UPSTREAM_FALLBACKS_FILE", tmp_path / "fallbacks"
    )

    with pytest.raises(MacblockError, match=r"failed to remove"):
        install.do_uninstall(force=False)
