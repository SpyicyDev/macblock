import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

cli_module = importlib.import_module("macblock.cli")
_parse_args = cli_module._parse_args


class TestCli(unittest.TestCase):
    def test_parser_status(self):
        cmd, args = _parse_args(["status"])
        self.assertEqual(cmd, "status")

    def test_parser_doctor(self):
        cmd, args = _parse_args(["doctor"])
        self.assertEqual(cmd, "doctor")

    def test_parser_enable(self):
        cmd, args = _parse_args(["enable"])
        self.assertEqual(cmd, "enable")

    def test_parser_disable(self):
        cmd, args = _parse_args(["disable"])
        self.assertEqual(cmd, "disable")

    def test_parser_pause(self):
        cmd, args = _parse_args(["pause", "10m"])
        self.assertEqual(cmd, "pause")
        self.assertEqual(args["duration"], "10m")

    def test_parser_install_force(self):
        cmd, args = _parse_args(["install", "--force"])
        self.assertEqual(cmd, "install")
        self.assertTrue(args["force"])

    def test_parser_no_args(self):
        cmd, args = _parse_args([])
        self.assertIsNone(cmd)

    def test_parser_sources_list(self):
        cmd, args = _parse_args(["sources", "list"])
        self.assertEqual(cmd, "sources")
        self.assertEqual(args["sources_cmd"], "list")

    def test_parser_sources_set(self):
        cmd, args = _parse_args(["sources", "set", "hagezi-pro"])
        self.assertEqual(cmd, "sources")
        self.assertEqual(args["sources_cmd"], "set")
        self.assertEqual(args["source"], "hagezi-pro")


if __name__ == "__main__":
    unittest.main()
