import importlib
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

pf = importlib.import_module("macblock.pf")


class TestPf(unittest.TestCase):
    def test_render_anchor_rules_includes_ipv4_ipv6_rdr(self):
        rules = pf.render_anchor_rules()
        self.assertIn("rdr pass on egress inet", rules)
        self.assertIn("rdr pass on egress inet6", rules)
        self.assertIn("port 53", rules)
        self.assertNotIn("user !=", rules)

    def test_render_anchor_rules_includes_no_rdr_for_excluded_interfaces(self):
        with tempfile.TemporaryDirectory() as d:
            exclude_file = Path(d) / "pf.exclude_interfaces"
            exclude_file.write_text("utun0\n", encoding="utf-8")

            old = getattr(pf, "PF_EXCLUDE_INTERFACES_FILE")
            try:
                setattr(pf, "PF_EXCLUDE_INTERFACES_FILE", exclude_file)
                rules = pf.render_anchor_rules()
                self.assertIn("no rdr on utun0 inet proto", rules)
                self.assertIn("no rdr on utun0 inet6 proto", rules)
            finally:
                setattr(pf, "PF_EXCLUDE_INTERFACES_FILE", old)

    def test_with_pf_block_inserts_rdr_anchor_before_filtering(self):
        conf = (
            "set limit {tables 10000, table-entries 400000}\n"
            "scrub-anchor \"com.apple/*\"\n"
            "nat-anchor \"com.apple/*\"\n"
            "rdr-anchor \"com.apple/*\"\n"
            "dummynet-anchor \"com.apple/*\"\n"
            "anchor \"com.apple/*\"\n"
            "load anchor \"com.apple\" from \"/etc/pf.anchors/com.apple\"\n"
        )
        new = pf._with_pf_block(conf)
        lines = new.splitlines()
        self.assertIn(pf._MARKER_BEGIN, new)
        self.assertIn(pf._MARKER_END, new)
        idx_macblock = lines.index(f"rdr-anchor \"{pf.APP_LABEL}\"")
        idx_comapple_rdr = lines.index('rdr-anchor "com.apple/*"')
        idx_anchor = lines.index('anchor "com.apple/*"')
        self.assertGreater(idx_macblock, idx_comapple_rdr)
        self.assertLess(idx_macblock, idx_anchor)

    def test_with_pf_block_is_idempotent(self):
        conf = (
            "scrub-anchor \"com.apple/*\"\n"
            "nat-anchor \"com.apple/*\"\n"
            "rdr-anchor \"com.apple/*\"\n"
            "dummynet-anchor \"com.apple/*\"\n"
            "anchor \"com.apple/*\"\n"
        )
        once = pf._with_pf_block(conf)
        twice = pf._with_pf_block(once)
        self.assertEqual(once, twice)

    def test_with_pf_block_relocates_old_block(self):
        base = (
            "scrub-anchor \"com.apple/*\"\n"
            "nat-anchor \"com.apple/*\"\n"
            "rdr-anchor \"com.apple/*\"\n"
            "dummynet-anchor \"com.apple/*\"\n"
            "anchor \"com.apple/*\"\n"
            "load anchor \"com.apple\" from \"/etc/pf.anchors/com.apple\"\n"
        )
        old = (
            base
            + "\n"
            + pf._MARKER_BEGIN
            + "\n"
            + f"rdr-anchor \"{pf.APP_LABEL}\"\n"
            + f"anchor \"{pf.APP_LABEL}\"\n"
            + f"load anchor \"{pf.APP_LABEL}\" from \"{pf.PF_ANCHOR_FILE}\"\n"
            + pf._MARKER_END
            + "\n"
        )
        new = pf._with_pf_block(old)
        lines = new.splitlines()
        self.assertIn(f"rdr-anchor \"{pf.APP_LABEL}\"", lines)
        self.assertNotIn(f"anchor \"{pf.APP_LABEL}\"", lines)
        self.assertNotIn(f"load anchor \"{pf.APP_LABEL}\"", lines)
        self.assertLess(lines.index(f"rdr-anchor \"{pf.APP_LABEL}\""), lines.index('anchor "com.apple/*"'))


if __name__ == "__main__":
    unittest.main()
