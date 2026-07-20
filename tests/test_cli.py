"""Tests for the command-line entry point.

Importing ``insightflow.main`` must not require PySide6 -- Qt is imported inside
``main()``. That keeps ``--help`` and these tests working headlessly.
"""

import unittest

from insightflow.main import parse_args


class TestParseArgs(unittest.TestCase):
    def test_defaults(self):
        args = parse_args([])
        self.assertFalse(args.demo)
        self.assertFalse(args.no_cache)

    def test_demo_flag(self):
        self.assertTrue(parse_args(["--demo"]).demo)

    def test_no_cache_flag(self):
        self.assertTrue(parse_args(["--no-cache"]).no_cache)

    def test_flags_combine(self):
        args = parse_args(["--demo", "--no-cache"])
        self.assertTrue(args.demo and args.no_cache)

    def test_unknown_flag_exits(self):
        with self.assertRaises(SystemExit):
            parse_args(["--wat"])


class TestHeadlessImport(unittest.TestCase):
    def test_importing_main_does_not_pull_in_qt(self):
        import insightflow.main as entry

        self.assertFalse(
            hasattr(entry, "QApplication"),
            "Qt is imported at module scope; --help would fail without PySide6.",
        )


if __name__ == "__main__":
    unittest.main()
