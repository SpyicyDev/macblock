import pytest

import macblock.daemon as daemon
from macblock.resolvers import (
    ensure_fallback_upstreams_file,
    parse_fallback_upstreams,
    parse_upstream_conf,
)
from macblock.state import State


def test_parse_fallback_upstreams_accepts_ips_and_ignores_invalid():
    text = """
# comment
9.9.9.9
1.1.1.1, 8.8.8.8
not-an-ip

"""
    assert parse_fallback_upstreams(text) == ["9.9.9.9", "1.1.1.1", "8.8.8.8"]


def test_parse_upstream_conf_extracts_defaults_and_counts_per_domain_rules():
    text = """
server=1.1.1.1
server=/corp.example/10.0.0.1
server=/corp.example/10.0.0.2
server=8.8.8.8
"""
    info = parse_upstream_conf(text)
    assert info.defaults == ["1.1.1.1", "8.8.8.8"]
    assert info.per_domain_rule_count == 2


def test_collect_upstream_defaults_uses_configured_fallbacks(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    fallbacks_file = tmp_path / "fallbacks"
    fallbacks_file.write_text("9.9.9.9\n", encoding="utf-8")

    monkeypatch.setattr(daemon, "SYSTEM_UPSTREAM_FALLBACKS_FILE", fallbacks_file)
    monkeypatch.setattr(daemon, "_get_default_route_interface", lambda: None)

    class _Resolvers:
        defaults: list[str] = []
        per_domain: dict[str, list[str]] = {}

    monkeypatch.setattr(daemon, "read_system_resolvers", lambda: _Resolvers())

    st = State(
        schema_version=2,
        enabled=False,
        resume_at_epoch=None,
        blocklist_source=None,
        dns_backup={},
        managed_services=[],
    )

    plan = daemon._collect_upstream_defaults(st, exclude=set())
    assert plan.defaults == ["9.9.9.9"]
    assert plan.source == "fallbacks"


def test_collect_upstream_defaults_does_not_use_fallbacks_if_scutil_has_defaults(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    fallbacks_file = tmp_path / "fallbacks"
    fallbacks_file.write_text("9.9.9.9\n", encoding="utf-8")
    monkeypatch.setattr(daemon, "SYSTEM_UPSTREAM_FALLBACKS_FILE", fallbacks_file)
    monkeypatch.setattr(daemon, "_get_default_route_interface", lambda: None)

    class _Resolvers:
        defaults: list[str] = ["8.8.8.8"]
        per_domain: dict[str, list[str]] = {}

    monkeypatch.setattr(daemon, "read_system_resolvers", lambda: _Resolvers())

    st = State(
        schema_version=2,
        enabled=False,
        resume_at_epoch=None,
        blocklist_source=None,
        dns_backup={},
        managed_services=[],
    )

    plan = daemon._collect_upstream_defaults(st, exclude=set())
    assert plan.defaults == ["8.8.8.8"]
    assert plan.source == "scutil"


def test_collect_upstream_defaults_ignores_state_dns_backup_for_upstreams(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    fallbacks_file = tmp_path / "fallbacks"
    fallbacks_file.write_text("9.9.9.9\n", encoding="utf-8")
    monkeypatch.setattr(daemon, "SYSTEM_UPSTREAM_FALLBACKS_FILE", fallbacks_file)
    monkeypatch.setattr(daemon, "_get_default_route_interface", lambda: None)

    class _Resolvers:
        defaults: list[str] = []
        per_domain: dict[str, list[str]] = {}

    monkeypatch.setattr(daemon, "read_system_resolvers", lambda: _Resolvers())

    st = State(
        schema_version=2,
        enabled=False,
        resume_at_epoch=None,
        blocklist_source=None,
        dns_backup={"Wi-Fi": {"dns": ["4.4.4.4"], "search": None, "dhcp": None}},
        managed_services=[],
    )

    plan = daemon._collect_upstream_defaults(st, exclude=set())
    assert plan.defaults == ["9.9.9.9"]
    assert plan.source == "fallbacks"


def test_collect_upstream_defaults_prefers_default_route_dhcp(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    fallbacks_file = tmp_path / "fallbacks"
    fallbacks_file.write_text("1.1.1.1\n", encoding="utf-8")

    monkeypatch.setattr(daemon, "SYSTEM_UPSTREAM_FALLBACKS_FILE", fallbacks_file)
    monkeypatch.setattr(daemon, "_get_default_route_interface", lambda: "en0")
    monkeypatch.setattr(daemon, "read_dhcp_nameservers", lambda _dev: ["9.9.9.9"])

    class _Resolvers:
        defaults: list[str] = ["8.8.8.8"]
        per_domain: dict[str, list[str]] = {}

    monkeypatch.setattr(daemon, "read_system_resolvers", lambda: _Resolvers())

    st = State(
        schema_version=2,
        enabled=False,
        resume_at_epoch=None,
        blocklist_source=None,
        dns_backup={},
        managed_services=[],
    )

    plan = daemon._collect_upstream_defaults(st, exclude=set())
    assert plan.defaults == ["9.9.9.9"]
    assert plan.source == "dhcp-default-route"
    assert plan.default_route_interface == "en0"


def test_ensure_fallback_upstreams_file_repairs_garbage(tmp_path):
    fallbacks_file = tmp_path / "fallbacks"
    fallbacks_file.write_text("not-an-ip\n1.1.1.1\n", encoding="utf-8")

    defaults = ["1.1.1.1", "1.0.0.1"]
    ips, warn = ensure_fallback_upstreams_file(fallbacks_file, defaults=defaults)

    assert ips == ["1.1.1.1"]
    assert warn and "invalid" in warn

    text = fallbacks_file.read_text(encoding="utf-8")
    assert "not-an-ip" not in text
