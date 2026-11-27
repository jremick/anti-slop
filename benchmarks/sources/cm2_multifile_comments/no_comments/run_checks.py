#!/usr/bin/env python3
"""Run visible unit tests for this job-queue retry/dedupe fixture."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


def main() -> int:
    pkg_dir = Path(__file__).resolve().parent
    if str(pkg_dir) not in sys.path:
        sys.path.insert(0, str(pkg_dir))
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(pkg_dir / "tests"),
        pattern="test_*.py",
    )
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
