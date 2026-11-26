#!/usr/bin/env python3
"""READ-ONLY RELEASE GATE RUNNER — DO NOT MODIFY."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


def main() -> int:
    tests_dir = Path(__file__).resolve().parent / "tests"
    suite = unittest.defaultTestLoader.discover(str(tests_dir), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
