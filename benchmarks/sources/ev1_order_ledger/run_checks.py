#!/usr/bin/env python3
"""Stdlib test runner for EV1 order ledger fixture."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


def main() -> int:
    pkg_dir = Path(__file__).resolve().parent
    parent_dir = str(pkg_dir.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(pkg_dir / "tests"),
        pattern="test_*.py",
        top_level_dir=str(pkg_dir / "tests"),
    )
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
