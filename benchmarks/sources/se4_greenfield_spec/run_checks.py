#!/usr/bin/env python3
"""Run frozen smoke tests for se4_greenfield_spec."""

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
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
