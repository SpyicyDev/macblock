# pyright: reportMissingImports=false

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_DEFAULT_PKG = "mac" + "block"
_BLOCKLISTS_MODULE = os.environ.get("MACBLOCK_BLOCKLISTS_MODULE") or (_DEFAULT_PKG + "." + "blocklists")
compile_blocklist = importlib.import_module(_BLOCKLISTS_MODULE).compile_blocklist  # pyright: ignore[reportMissingImports]


class TestBlocklists(unittest.TestCase):
    def test_compile_applies_allow_and_deny(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            raw = root / "raw"
            allow = root / "allow"
            deny = root / "deny"
            out = root / "out"

            raw.write_text("0.0.0.0 ads.example\n0.0.0.0 tracker.example\n", encoding="utf-8")
            allow.write_text("ads.example\n", encoding="utf-8")
            deny.write_text("extra.example\n", encoding="utf-8")

            count = compile_blocklist(raw, allow, deny, out)
            self.assertEqual(count, 2)
            text = out.read_text(encoding="utf-8")
            self.assertIn("server=/tracker.example/\n", text)
            self.assertIn("server=/extra.example/\n", text)
            self.assertNotIn("ads.example", text)


if __name__ == "__main__":
    unittest.main()
