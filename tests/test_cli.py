from macblock.cli import _parse_args


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
    assert args["stderr"] is False


def test_parser_logs_stderr_sets_stream():
    cmd, args = _parse_args(["logs", "--stderr"])
    assert cmd == "logs"
    assert args["stream"] == "stderr"
    assert args["stderr"] is True


def test_parser_logs_stream_overrides_alias():
    cmd, args = _parse_args(["logs", "--stderr", "--stream", "stdout"])
    assert cmd == "logs"
    assert args["stream"] == "stdout"
