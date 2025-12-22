from pathlib import Path

from macblock.blocklists import compile_blocklist


def test_compile_applies_allow_and_deny(tmp_path: Path):
    raw = tmp_path / "raw"
    allow = tmp_path / "allow"
    deny = tmp_path / "deny"
    out = tmp_path / "out"

    raw.write_text("0.0.0.0 ads.example\n0.0.0.0 tracker.example\n", encoding="utf-8")
    allow.write_text("ads.example\n", encoding="utf-8")
    deny.write_text("extra.example\n", encoding="utf-8")

    count = compile_blocklist(raw, allow, deny, out)
    assert count == 2

    text = out.read_text(encoding="utf-8")
    assert "server=/tracker.example/\n" in text
    assert "server=/extra.example/\n" in text
    assert "ads.example" not in text
