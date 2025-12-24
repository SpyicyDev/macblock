from pathlib import Path

from macblock.dns_test import _find_blocklist_match, _interpret_result


def test_find_blocklist_match_exact_and_suffix(tmp_path: Path):
    blocklist = tmp_path / "blocklist.conf"
    blocklist.write_text(
        "server=/ads.example/\nserver=/tracker.example/\n", encoding="utf-8"
    )

    match, err = _find_blocklist_match("ads.example", blocklist_path=blocklist)
    assert err is None
    assert match == "ads.example"

    match, err = _find_blocklist_match("sub.ads.example", blocklist_path=blocklist)
    assert err is None
    assert match == "ads.example"

    match, err = _find_blocklist_match("example.com", blocklist_path=blocklist)
    assert err is None
    assert match is None


def test_find_blocklist_match_missing_file(tmp_path: Path):
    missing = tmp_path / "missing.conf"
    match, err = _find_blocklist_match("ads.example", blocklist_path=missing)
    assert match is None
    assert err is not None


def test_interpret_nxdomain_blocked_when_in_blocklist():
    dig_out = """;; ->>HEADER<<- opcode: QUERY, status: NXDOMAIN, id: 1234\n"""
    status, _ = _interpret_result(
        dig_out, "ads.example", blocklist_match="ads.example", blocklist_error=None
    )
    assert status == "BLOCKED"


def test_interpret_nxdomain_not_blocked_when_not_in_blocklist():
    dig_out = """;; ->>HEADER<<- opcode: QUERY, status: NXDOMAIN, id: 1234\n"""
    status, _ = _interpret_result(
        dig_out, "example.com", blocklist_match=None, blocklist_error=None
    )
    assert status == "NXDOMAIN"
