import importlib
import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

build_parser = importlib.import_module("macblock.cli").build_parser


class TestCli(unittest.TestCase):
    def test_parser_smoke(self):
        p = build_parser()
        args = p.parse_args(["status"])
        self.assertEqual(args.cmd, "status")


if __name__ == "__main__":
    unittest.main()
