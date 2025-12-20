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


if __name__ == "__main__":
    unittest.main()
