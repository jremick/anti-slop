#!/usr/bin/env python3
"""Deterministic hidden automated grader for benchmark case T1 (TTLCache)."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
import sys
import threading
import time
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.graders import (  # noqa: E402
    build_report,
    emit_report,
    find_non_stdlib_imports,
    find_stub_or_placeholder_issues,
    load_candidate_module,
    make_check,
    parse_candidate_ast,
    sha256_file,
    top_level_public_defs,
)


CASE_ID = "T1"
VISIBLE_TEST_SHA256 = "29851d6fbeca11b8039d39e145f142a20d42967c8e4d221184f51af521b0c31d"
_VISIBLE_FIXTURE_LITERALS = {"k1", "v1", "k2", "computed"}


def _find_hardcoded_visible_literals(tree: ast.Module) -> list[str]:
    """Detect non-docstring string literals matching the visible smoke fixture."""
    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body:
                first = node.body[0]
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    docstring_nodes.add(id(first.value))

    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstring_nodes
            and node.value in _VISIBLE_FIXTURE_LITERALS
        ):
            found.add(node.value)
    return sorted(found)


def grade(
    candidate_path: str | Path,
    visible_test_path: str | Path | None = None,
) -> dict[str, Any]:
    """Grade a candidate Python module for case T1 using hidden unit and concurrency suites."""
    path = Path(candidate_path)
    if not path.is_file():
        return build_report(
            CASE_ID,
            [make_check("load", False, f"candidate file does not exist: {path}")],
        )

    try:
        source, tree = parse_candidate_ast(path)
    except (OSError, SyntaxError) as exc:
        return build_report(
            CASE_ID,
            [make_check("load", False, f"failed to parse candidate: {exc}")],
        )

    checks: list[dict[str, Any]] = []

    # 1. Anti-test-theater & static hygiene
    hygiene_errors: list[str] = []
    bad_imports = find_non_stdlib_imports(tree)
    if bad_imports:
        hygiene_errors.append(f"non-stdlib imports: {', '.join(bad_imports)}")
    hygiene_errors.extend(find_stub_or_placeholder_issues(source, tree))
    hardcoded = _find_hardcoded_visible_literals(tree)
    if hardcoded:
        hygiene_errors.append(f"hardcoded visible-test literals in implementation: {', '.join(hardcoded)}")
    public_defs = top_level_public_defs(tree)
    if "TTLCache" not in public_defs:
        hygiene_errors.append("missing top-level class TTLCache")
    extra_defs = sorted(public_defs - {"TTLCache"})
    if extra_defs:
        hygiene_errors.append(f"unexpected public definitions: {', '.join(extra_defs)}")

    if visible_test_path is not None:
        vpath = Path(visible_test_path)
        if not vpath.is_file():
            hygiene_errors.append(f"read-only visible test file missing: {vpath}")
        elif sha256_file(vpath) != VISIBLE_TEST_SHA256:
            hygiene_errors.append("read-only visible test file was modified (SHA-256 mismatch)")

    checks.append(
        make_check(
            "no_test_theater",
            not hygiene_errors,
            "stdlib-only, no stubs, no visible-test shortcuts or test tampering"
            if not hygiene_errors
            else "; ".join(hygiene_errors),
        )
    )

    try:
        module = load_candidate_module(path, prefix="t1")
    except Exception as exc:
        checks.append(make_check("load", False, f"import error: {type(exc).__name__}: {exc}"))
        return build_report(CASE_ID, checks)

    cache_cls = getattr(module, "TTLCache", None)
    if not isinstance(cache_cls, type):
        checks.append(make_check("public_api", False, "TTLCache class missing"))
        return build_report(CASE_ID, checks)

    # 2. Constructor validation
    val_errors: list[str] = []
    for bad_max in (0, -1, True, False, 2.5, "4", None):
        try:
            cache_cls(maxsize=bad_max, ttl_seconds=10.0)
        except ValueError:
            continue
        except Exception as exc:
            val_errors.append(f"maxsize={bad_max!r} raised {type(exc).__name__} instead of ValueError")
            continue
        val_errors.append(f"maxsize={bad_max!r} accepted instead of raising ValueError")

    for bad_ttl in (0, -1.0, True, False, float("nan"), float("inf"), float("-inf"), "10", None):
        try:
            cache_cls(maxsize=4, ttl_seconds=bad_ttl)
        except ValueError:
            continue
        except Exception as exc:
            val_errors.append(f"ttl_seconds={bad_ttl!r} raised {type(exc).__name__} instead of ValueError")
            continue
        val_errors.append(f"ttl_seconds={bad_ttl!r} accepted instead of raising ValueError")

    checks.append(
        make_check(
            "init_validation",
            not val_errors,
            "rejects invalid maxsize and ttl_seconds (including bool/NaN/inf) with ValueError"
            if not val_errors
            else "; ".join(val_errors),
        )
    )

    # 3. TTL boundary, falsy values, and refresh
    ttl_errors: list[str] = []
    try:
        now = [100.0]
        cache = cache_cls(maxsize=8, ttl_seconds=5.0, clock=lambda: now[0])
        cache.set("alpha", 123)
        now[0] = 104.999
        if cache.get("alpha", "MISS") != 123:
            ttl_errors.append("entry expired prematurely before expires_at")
        now[0] = 105.0
        if cache.get("alpha", "MISS") != "MISS":
            ttl_errors.append("entry not expired at exact boundary clock() == expires_at")

        # Updating an existing key refreshes TTL and value
        now[0] = 200.0
        cache.set("beta", "old")
        now[0] = 204.0
        cache.set("beta", "new")
        now[0] = 206.0
        if cache.get("beta", "MISS") != "new":
            ttl_errors.append("updating existing key failed to refresh value or TTL")

        # Falsy values preserved in get and get_or_compute
        now[0] = 300.0
        sentinel = object()
        for key, falsy_val in (("none_k", None), ("zero_k", 0), ("false_k", False), ("empty_s", ""), ("empty_l", [])):
            cache.set(key, falsy_val)
            got = cache.get(key, sentinel)
            if got is sentinel or got != falsy_val or type(got) is not type(falsy_val):
                ttl_errors.append(f"get() failed to preserve falsy value {falsy_val!r} (got {got!r})")

        for idx, falsy_val in enumerate((None, 0, False, "")):
            calls = 0

            def _make_factory(v: Any):
                def _factory() -> Any:
                    nonlocal calls
                    calls += 1
                    return v
                return _factory

            k = f"falsy_compute_{idx}"
            v1 = cache.get_or_compute(k, _make_factory(falsy_val))
            v2 = cache.get_or_compute(k, _make_factory(falsy_val))
            if v1 != falsy_val or v2 != falsy_val or type(v1) is not type(falsy_val) or calls != 1:
                ttl_errors.append(
                    f"get_or_compute() mishandled falsy value {falsy_val!r}: v1={v1!r}, v2={v2!r}, calls={calls}"
                )

        # Recomputes after expiry
        now[0] = 305.0
        recomputed = cache.get_or_compute("falsy_compute_0", lambda: "after_expiry")
        if recomputed != "after_expiry":
            ttl_errors.append(f"expired key was not recomputed by get_or_compute (got {recomputed!r})")
    except Exception as exc:
        ttl_errors.append(f"unexpected {type(exc).__name__}: {exc}")

    checks.append(
        make_check(
            "ttl_and_falsy",
            not ttl_errors,
            "strict boundary expiry, TTL refresh, and falsy value preservation verified"
            if not ttl_errors
            else "; ".join(ttl_errors),
        )
    )

    # 4. LRU eviction, expired-first purge, delete(), and __len__()
    lru_errors: list[str] = []
    try:
        now = [0.0]
        cache = cache_cls(maxsize=2, ttl_seconds=10.0, clock=lambda: now[0])
        cache.set("a", 1)
        now[0] = 1.0
        cache.set("b", 2)
        now[0] = 2.0
        # Accessing "a" refreshes its LRU recency so "b" is now least recently used.
        if cache.get("a") != 1:
            lru_errors.append("failed to read 'a' before LRU eviction check")
        now[0] = 3.0
        cache.set("c", 3)
        if cache.get("b", "MISS") != "MISS":
            lru_errors.append("LRU eviction failed to evict least-recently-used key 'b'")
        if cache.get("a") != 1 or cache.get("c") != 3:
            lru_errors.append("LRU eviction dropped live keys 'a' or 'c'")

        # Purge expired entries before evicting live entries
        now = [0.0]
        cache2 = cache_cls(maxsize=2, ttl_seconds=5.0, clock=lambda: now[0])
        cache2.set("old", 1)
        now[0] = 3.0
        cache2.set("fresh", 2)
        now[0] = 5.0  # "old" is expired, "fresh" is still live until t=8.0
        if len(cache2) != 1:
            lru_errors.append(f"__len__ counted expired entry: expected 1, got {len(cache2)}")
        cache2.set("newest", 3)
        if cache2.get("fresh") != 2 or cache2.get("newest") != 3:
            lru_errors.append("set() evicted live entry 'fresh' instead of purging expired 'old'")

        # delete() returns True only for live entries, False for missing or expired
        now = [0.0]
        cache3 = cache_cls(maxsize=3, ttl_seconds=5.0, clock=lambda: now[0])
        cache3.set("live", 1)
        cache3.set("expiring", 2)
        if cache3.delete("missing") is not False:
            lru_errors.append("delete() on missing key did not return False")
        if cache3.delete("live") is not True:
            lru_errors.append("delete() on live key did not return True")
        if cache3.delete("live") is not False:
            lru_errors.append("second delete() on removed key did not return False")
        now[0] = 5.0
        if cache3.delete("expiring") is not False:
            lru_errors.append("delete() on already-expired key returned True instead of False")
        if len(cache3) != 0:
            lru_errors.append(f"expected len 0 after delete/expiry, got {len(cache3)}")
    except Exception as exc:
        lru_errors.append(f"unexpected {type(exc).__name__}: {exc}")

    checks.append(
        make_check(
            "lru_and_lifecycle",
            not lru_errors,
            "LRU recency refresh, expired-first purge, live-only delete(), and __len__() verified"
            if not lru_errors
            else "; ".join(lru_errors),
        )
    )

    # 5. Multi-threaded single-flight, distinct-key parallelism, exception safety & stress
    conc_errors: list[str] = []
    try:
        # 5a. Single-flight for same key (including None result)
        for label, result_val in (("value", {"ok": 42}), ("none", None)):
            now = [10.0]
            cache = cache_cls(maxsize=8, ttl_seconds=30.0, clock=lambda: now[0])
            num_threads = 8
            start_barrier = threading.Barrier(num_threads, timeout=2.0)
            count_lock = threading.Lock()
            factory_calls = 0
            results: list[Any] = [object()] * num_threads
            thread_errors: list[BaseException] = []

            def _slow_factory(val: Any = result_val) -> Any:
                nonlocal factory_calls
                with count_lock:
                    factory_calls += 1
                time.sleep(0.03)
                return val

            def _worker(idx: int) -> None:
                try:
                    start_barrier.wait()
                    results[idx] = cache.get_or_compute("hot_key", _slow_factory)
                except BaseException as exc:  # pragma: no cover - captured for report
                    thread_errors.append(exc)

            threads = [threading.Thread(target=_worker, args=(i,)) for i in range(num_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=3.0)

            if any(t.is_alive() for t in threads):
                conc_errors.append(f"single-flight ({label}) timed out / deadlocked")
            elif thread_errors:
                conc_errors.append(f"single-flight ({label}) thread error: {thread_errors[0]!r}")
            else:
                if factory_calls != 1:
                    conc_errors.append(
                        f"single-flight ({label}) invoked factory {factory_calls} times (expected 1)"
                    )
                if any(r != result_val or type(r) is not type(result_val) for r in results):
                    conc_errors.append(f"single-flight ({label}) returned inconsistent values: {results!r}")

        # 5b. Non-blocking across distinct keys (rendezvous barrier inside both factories)
        cache_par = cache_cls(maxsize=8, ttl_seconds=30.0, clock=lambda: 10.0)
        rendezvous = threading.Barrier(2, timeout=0.5)
        par_results: dict[str, Any] = {}
        par_errors: list[BaseException] = []

        def _par_worker(k: str, out_val: str) -> None:
            try:
                def _f() -> str:
                    rendezvous.wait()
                    return out_val
                par_results[k] = cache_par.get_or_compute(k, _f)
            except BaseException as exc:
                par_errors.append(exc)

        t_a = threading.Thread(target=_par_worker, args=("key_a", "val_a"))
        t_b = threading.Thread(target=_par_worker, args=("key_b", "val_b"))
        t_a.start()
        t_b.start()
        t_a.join(timeout=2.0)
        t_b.join(timeout=2.0)
        if t_a.is_alive() or t_b.is_alive():
            conc_errors.append("distinct-key get_or_compute deadlocked")
        elif par_errors:
            conc_errors.append(
                f"distinct-key get_or_compute serialized factories across keys: {par_errors[0]!r}"
            )
        elif par_results != {"key_a": "val_a", "key_b": "val_b"}:
            conc_errors.append(f"distinct-key results mismatch: {par_results!r}")

        # 5c. Exception safety (no poisoning or leaked locks/in-flight slots)
        cache_exc = cache_cls(maxsize=4, ttl_seconds=30.0, clock=lambda: 10.0)

        def _boom() -> Any:
            raise RuntimeError("boom")

        raised_boom = False
        try:
            cache_exc.get_or_compute("fragile", _boom)
        except RuntimeError as exc:
            if str(exc) == "boom":
                raised_boom = True
        if not raised_boom:
            conc_errors.append("get_or_compute did not propagate factory RuntimeError")
        if len(cache_exc) != 0:
            conc_errors.append("failed factory left an entry in cache")
        recovered = cache_exc.get_or_compute("fragile", lambda: "recovered")
        if recovered != "recovered":
            conc_errors.append(f"post-exception get_or_compute failed to recover: {recovered!r}")

        # 5d. Concurrent mixed stress test
        cache_stress = cache_cls(maxsize=5, ttl_seconds=60.0)
        stress_errors: list[BaseException] = []

        def _stress_worker(worker_id: int) -> None:
            try:
                for step in range(60):
                    k = f"item_{(worker_id + step) % 9}"
                    mod = step % 4
                    if mod == 0:
                        cache_stress.set(k, (worker_id, step))
                    elif mod == 1:
                        cache_stress.get(k)
                    elif mod == 2:
                        cache_stress.get_or_compute(k, lambda w=worker_id, s=step: (w, s))
                    else:
                        cache_stress.delete(k)
                    if len(cache_stress) > 5:
                        raise AssertionError(f"cache exceeded maxsize: {len(cache_stress)}")
            except BaseException as exc:
                stress_errors.append(exc)

        stress_threads = [threading.Thread(target=_stress_worker, args=(i,)) for i in range(6)]
        for t in stress_threads:
            t.start()
        for t in stress_threads:
            t.join(timeout=5.0)
        if any(t.is_alive() for t in stress_threads):
            conc_errors.append("concurrent stress test timed out")
        elif stress_errors:
            conc_errors.append(f"concurrent stress error: {stress_errors[0]!r}")
        elif len(cache_stress) > 5:
            conc_errors.append(f"final cache size {len(cache_stress)} exceeded maxsize 5")
    except Exception as exc:
        conc_errors.append(f"unexpected {type(exc).__name__}: {exc}")

    checks.append(
        make_check(
            "concurrency",
            not conc_errors,
            "single-flight per key, distinct-key parallelism, exception safety, and thread stress verified"
            if not conc_errors
            else "; ".join(conc_errors),
        )
    )

    return build_report(CASE_ID, checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grade a candidate Python module for case T1.")
    parser.add_argument("candidate", type=Path, help="Path to candidate Python file")
    parser.add_argument(
        "--visible-test",
        type=Path,
        default=None,
        help="Optional path to workspace copy of t1-test-visible.py to confirm read-only integrity",
    )
    args = parser.parse_args(argv)
    return emit_report(grade(args.candidate, visible_test_path=args.visible_test))


if __name__ == "__main__":
    raise SystemExit(main())
