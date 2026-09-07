#!/usr/bin/env python3

from pathlib import Path
import importlib.util
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("upstream", ROOT / "scripts/upstream.py")
assert SPEC and SPEC.loader
upstream = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = upstream
SPEC.loader.exec_module(upstream)


class UpstreamTests(unittest.TestCase):
    def test_parse_and_sort(self) -> None:
        fixture = (ROOT / "tests/fixtures/index.html").read_text(encoding="utf-8")
        packages = upstream.sorted_packages(
            upstream.parse_index(fixture, "https://example.invalid/workbuddy/")
        )
        self.assertEqual(
            [(item.version, item.arch) for item in packages],
            [("5.4.0", "amd64"), ("5.4.0", "arm64"), ("5.4.5", "amd64")],
        )
        self.assertEqual(
            packages[-1].url,
            "https://example.invalid/workbuddy/workbuddy_5.4.5_amd64.deb",
        )


if __name__ == "__main__":
    unittest.main()

