"""Read-only visible smoke tests for T1.

Do not edit, weaken, or skip assertions in this file.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import unittest


def _resolve_candidate_path() -> Path:
    env_target = os.environ.get("T1_CANDIDATE")
    if env_target:
        return Path(env_target)
    this_file = Path(__file__).resolve()
    for arg in sys.argv[1:]:
        if arg.startswith("-"):
            continue
        candidate = Path(arg)
        try:
            if candidate.resolve() == this_file:
                continue
        except OSError:
            pass
        if candidate.suffix == ".py" or candidate.is_file():
            return candidate
    return Path(__file__).with_name("t1-cache.py")


def _load_cache_module():
    target = _resolve_candidate_path()
    spec = importlib.util.spec_from_file_location("t1_cache_candidate", target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VisibleCacheSmokeTests(unittest.TestCase):
    def test_basic_set_get(self) -> None:
        mod = _load_cache_module()
        now = [100.0]
        cache = mod.TTLCache(maxsize=4, ttl_seconds=10.0, clock=lambda: now[0])
        cache.set("k1", "v1")
        self.assertEqual(cache.get("k1"), "v1")

    def test_expiry_after_ttl(self) -> None:
        mod = _load_cache_module()
        now = [100.0]
        cache = mod.TTLCache(maxsize=4, ttl_seconds=10.0, clock=lambda: now[0])
        cache.set("k1", "v1")
        now[0] = 120.0
        self.assertIsNone(cache.get("k1"))

    def test_single_threaded_get_or_compute(self) -> None:
        mod = _load_cache_module()
        now = [100.0]
        calls = 0

        def factory() -> str:
            nonlocal calls
            calls += 1
            return "computed"

        cache = mod.TTLCache(maxsize=4, ttl_seconds=10.0, clock=lambda: now[0])
        self.assertEqual(cache.get_or_compute("k2", factory), "computed")
        self.assertEqual(cache.get_or_compute("k2", factory), "computed")
        self.assertEqual(calls, 1)

    def test_cached_zero_not_recomputed(self) -> None:
        mod = _load_cache_module()
        now = [100.0]
        calls = 0

        def factory() -> int:
            nonlocal calls
            calls += 1
            return 0

        cache = mod.TTLCache(maxsize=4, ttl_seconds=10.0, clock=lambda: now[0])
        self.assertEqual(cache.get_or_compute("zero", factory), 0)
        self.assertEqual(cache.get_or_compute("zero", factory), 0)
        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest_argv = [sys.argv[0]] + [arg for arg in sys.argv[1:] if arg.startswith("-")]
    unittest.main(argv=unittest_argv)
