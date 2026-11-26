"""Baseline smoke tests for rw1_tomlkit (read-only)."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

import tomlkit  # noqa: E402
from tomlkit.exceptions import KeyAlreadyPresent, TOMLKitError  # noqa: E402


class TomlkitBaselineSmokeTests(unittest.TestCase):
    def test_roundtrip_and_comments(self) -> None:
        src = "# header\n[project]\nname = \"demo\"  # inline\nversion = \"1.0\"\n"
        doc = tomlkit.parse(src)
        self.assertEqual(doc["project"]["name"], "demo")
        self.assertEqual(doc.as_string(), src)

    def test_valid_out_of_order_super_table_from_single_dotted_key(self) -> None:
        src = "[a.b.c]\n[a]\nb.z = 1\n"
        doc = tomlkit.parse(src)
        self.assertEqual(doc.as_string(), src)
        self.assertEqual(doc.unwrap(), {"a": {"b": {"c": {}, "z": 1}}})

    def test_duplicate_concrete_table_rejected(self) -> None:
        with self.assertRaises((KeyAlreadyPresent, TOMLKitError)):
            tomlkit.parse("[a.b]\nc = 1\n\n[a.b]\nd = 2\n")

    def test_aot_valid_dict_assignment(self) -> None:
        doc = tomlkit.parse("[[a]]\nx = 1\n[[a]]\nx = 2\n")
        doc["a"][:1] = [{"x": 9}]
        self.assertEqual(doc.unwrap(), {"a": [{"x": 9}, {"x": 2}]})

    def test_shallow_copy_preserves_content(self) -> None:
        doc = tomlkit.parse("[t]\nx = 1\n")
        cloned = copy.copy(doc)
        self.assertEqual(cloned.as_string(), doc.as_string())


if __name__ == "__main__":
    unittest.main()
