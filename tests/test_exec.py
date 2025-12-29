import subprocess
from types import SimpleNamespace

import pytest

import macblock.exec as mbexec


def test_run_passes_explicit_encoding_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_run(cmd: list[str], **kwargs: object):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(mbexec.subprocess, "run", _fake_run)

    r = mbexec.run(["/bin/echo", "hi"], timeout=1.0)
    assert r.returncode == 0
    assert r.stdout == "ok\n"
    assert r.stderr == ""

    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["text"] is True
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"


def test_run_timeout_decodes_invalid_utf8_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run(cmd: list[str], **kwargs: object):
        raise subprocess.TimeoutExpired(cmd, 1.0, output=b"\xff", stderr=b"\xfe")

    monkeypatch.setattr(mbexec.subprocess, "run", _fake_run)

    r = mbexec.run(["/bin/sleep", "10"], timeout=1.0)
    assert r.returncode == 124
    assert "\ufffd" in r.stdout
    assert "\ufffd" in r.stderr
    assert "command timed out after 1.0s" in r.stderr
