import pytest

import macblock.cli as cli
from macblock.cli import _parse_args
from macblock.errors import MacblockError, PrivilegeError


def test_parser_status():
    cmd, _ = _parse_args(["status"])
    assert cmd == "status"


def test_parser_doctor():
    cmd, _ = _parse_args(["doctor"])
    assert cmd == "doctor"


def test_parser_enable():
    cmd, _ = _parse_args(["enable"])
    assert cmd == "enable"


def test_parser_disable():
    cmd, _ = _parse_args(["disable"])
    assert cmd == "disable"


def test_parser_pause():
    cmd, args = _parse_args(["pause", "10m"])
    assert cmd == "pause"
    assert args["duration"] == "10m"


def test_parser_install_force():
    cmd, args = _parse_args(["install", "--force"])
    assert cmd == "install"
    assert args["force"] is True


def test_parser_no_args():
    cmd, _ = _parse_args([])
    assert cmd == "status"


def test_parser_sources_list():
    cmd, args = _parse_args(["sources", "list"])
    assert cmd == "sources"
    assert args["sources_cmd"] == "list"


def test_parser_sources_set():
    cmd, args = _parse_args(["sources", "set", "hagezi-pro"])
    assert cmd == "sources"
    assert args["sources_cmd"] == "set"
    assert args["source"] == "hagezi-pro"


def test_parser_logs_defaults_to_auto_stream():
    cmd, args = _parse_args(["logs"])
    assert cmd == "logs"
    assert args["component"] == "daemon"
    assert args["lines"] == 200
    assert args["follow"] is False
    assert args["stream"] == "auto"


def test_parser_logs_stream_sets_stderr():
    cmd, args = _parse_args(["logs", "--stream", "stderr"])
    assert cmd == "logs"
    assert args["stream"] == "stderr"


def test_parser_logs_raises_on_unknown_flag():
    with pytest.raises(MacblockError, match=r"unknown flag for logs"):
        _parse_args(["logs", "--nope"])


def test_parser_update_raises_on_unknown_flag():
    with pytest.raises(MacblockError, match=r"unknown flag for update"):
        _parse_args(["update", "--nope"])


def test_parser_upstreams_list():
    cmd, args = _parse_args(["upstreams", "list"])
    assert cmd == "upstreams"
    assert args["upstreams_cmd"] == "list"
    assert args["ips"] == []


def test_parser_upstreams_set_with_ips():
    cmd, args = _parse_args(["upstreams", "set", "9.9.9.9", "1.1.1.1"])
    assert cmd == "upstreams"
    assert args["upstreams_cmd"] == "set"
    assert args["ips"] == ["9.9.9.9", "1.1.1.1"]


def test_parser_upstreams_reset():
    cmd, args = _parse_args(["upstreams", "reset"])
    assert cmd == "upstreams"
    assert args["upstreams_cmd"] == "reset"


def test_exec_sudo_raises_when_sudo_missing(monkeypatch: pytest.MonkeyPatch):
    def _which(cmd: str):
        if cmd == "sudo":
            return None
        return "/bin/echo"

    monkeypatch.setattr(cli.shutil, "which", _which)

    with pytest.raises(PrivilegeError, match="sudo not found"):
        cli._exec_sudo(["status"])


def test_exec_sudo_raises_when_recursing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MACBLOCK_ELEVATED", "1")
    monkeypatch.setattr(cli.shutil, "which", lambda _cmd: "/usr/bin/sudo")

    with pytest.raises(PrivilegeError, match="failed to elevate privileges"):
        cli._exec_sudo(["status"])


def test_exec_sudo_execs_with_exe_and_minimal_env(monkeypatch: pytest.MonkeyPatch):
    called: dict[str, object] = {}

    def _execve(path: str, argv: list[str], env: dict[str, str]):
        called["path"] = path
        called["argv"] = argv
        called["env"] = env
        raise RuntimeError("execve called")

    def _which(cmd: str):
        if cmd == "sudo":
            return "/usr/bin/sudo"
        if cmd == cli.sys.argv[0]:
            return "/opt/homebrew/bin/macblock"
        return None

    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("PYTHONPATH", "/tmp/dev")
    monkeypatch.setenv("MACBLOCK_BIN", "/tmp/macblock")
    monkeypatch.setenv("MACBLOCK_DNSMASQ_BIN", "/tmp/dnsmasq")

    monkeypatch.setattr(cli.shutil, "which", _which)
    monkeypatch.setattr(cli.os, "execve", _execve)

    with pytest.raises(RuntimeError, match="execve called"):
        cli._exec_sudo(["status"])

    assert called["path"] == "/usr/bin/sudo"
    argv = called["argv"]
    env = called["env"]

    assert isinstance(argv, list)
    assert "-E" not in argv
    assert argv[:2] == ["/usr/bin/sudo", "/opt/homebrew/bin/macblock"]

    assert isinstance(env, dict)
    assert env.get("MACBLOCK_ELEVATED") == "1"
    assert "PATH" not in env
    assert "PYTHONPATH" not in env
    assert "MACBLOCK_BIN" not in env
    assert "MACBLOCK_DNSMASQ_BIN" not in env


def test_exec_sudo_execs_with_python_module_when_exe_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    called: dict[str, object] = {}

    def _execve(path: str, argv: list[str], env: dict[str, str]):
        called["path"] = path
        called["argv"] = argv
        called["env"] = env
        raise RuntimeError("execve called")

    def _which(cmd: str):
        if cmd == "sudo":
            return "/usr/bin/sudo"
        return None

    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TERM", "xterm-256color")

    monkeypatch.setattr(cli.shutil, "which", _which)
    monkeypatch.setattr(cli.os, "execve", _execve)

    with pytest.raises(RuntimeError, match="execve called"):
        cli._exec_sudo(["status"])

    assert called["path"] == "/usr/bin/sudo"
    argv = called["argv"]
    env = called["env"]

    assert isinstance(argv, list)
    assert "-E" not in argv
    assert argv[:4] == ["/usr/bin/sudo", cli.sys.executable, "-m", "macblock"]

    assert isinstance(env, dict)
    assert env.get("MACBLOCK_ELEVATED") == "1"
    assert "PATH" not in env
