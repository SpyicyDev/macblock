import pytest

import macblock.daemon as daemon
from macblock.resolvers import parse_fallback_upstreams, parse_upstream_conf
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

    class _Resolvers:
        defaults: list[str] = []
        per_domain: dict[str, list[str]] = {}

    monkeypatch.setattr(daemon, "read_system_resolvers", lambda: _Resolvers())
    monkeypatch.setattr(daemon, "compute_managed_services", lambda exclude=None: [])

    st = State(
        schema_version=2,
        enabled=False,
        resume_at_epoch=None,
        blocklist_source=None,
        dns_backup={},
        managed_services=[],
        resolver_domains=[],
    )

    assert daemon._collect_upstream_defaults(st, exclude=set()) == ["9.9.9.9"]
