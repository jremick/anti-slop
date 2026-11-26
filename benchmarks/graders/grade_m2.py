#!/usr/bin/env python3
"""Deterministic multi-file workspace grader for benchmark case M2 (m2_jobqueue)."""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
from pathlib import Path
import sys
import threading
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.graders import (  # noqa: E402
    build_report,
    emit_report,
    find_non_stdlib_imports,
    find_stub_or_placeholder_issues,
    load_candidate_package,
    make_check,
    parse_candidate_ast,
    sha256_file,
)


CASE_ID = "M2"
PACKAGE_NAME = "m2_jobqueue"

READONLY_SHA256: dict[str, str] = {
    "tests/test_basic.py": "d7835d5369b09a0e19f527e88bb9bd23a125518fae78eb5b1332517b30155ea6",
}

EXPECTED_FILES: tuple[str, ...] = (
    "__init__.py",
    "errors.py",
    "metrics.py",
    "models.py",
    "scheduler.py",
    "store.py",
    "worker.py",
    "tests/test_basic.py",
)


def _resolve_package_dir(workspace: Path) -> Path | None:
    candidates = [
        workspace / "benchmarks" / "sources" / PACKAGE_NAME,
        workspace / PACKAGE_NAME,
        workspace,
    ]
    for cand in candidates:
        if cand.is_dir() and cand.name == PACKAGE_NAME and (cand / "__init__.py").is_file():
            return cand
    return None


def _has_ident_ref(tree: ast.Module, ident: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == ident:
            return True
        if isinstance(node, ast.arg) and node.arg == ident:
            return True
        if isinstance(node, ast.keyword) and node.arg == ident:
            return True
    return False


def grade(workspace_path: str | Path, stage: int = 2) -> dict[str, Any]:
    """Grade an m2_jobqueue workspace snapshot for Stage 1 or Stage 2."""
    if stage not in (1, 2):
        return build_report(CASE_ID, [make_check("stage", False, f"unsupported stage {stage}; expected 1 or 2")])

    pkg_dir = _resolve_package_dir(Path(workspace_path))
    if pkg_dir is None:
        return build_report(
            CASE_ID,
            [make_check("load", False, f"could not locate {PACKAGE_NAME} package under {workspace_path}")],
        )

    missing_files = [rel for rel in EXPECTED_FILES if not (pkg_dir / rel).is_file()]
    if missing_files:
        return build_report(
            CASE_ID,
            [make_check("load", False, f"missing expected package files: {', '.join(missing_files)}")],
        )

    parsed_files: dict[str, tuple[str, ast.Module]] = {}
    parse_errors: list[str] = []
    for py_path in sorted(pkg_dir.rglob("*.py")):
        if "__pycache__" in py_path.parts:
            continue
        rel = str(py_path.relative_to(pkg_dir)).replace("\\", "/")
        try:
            parsed_files[rel] = parse_candidate_ast(py_path)
        except (OSError, SyntaxError) as exc:
            parse_errors.append(f"{rel}: {exc}")
    if parse_errors:
        return build_report(CASE_ID, [make_check("load", False, "; ".join(parse_errors))])

    checks: list[dict[str, Any]] = []

    # 1. Read-only test immutability, stdlib-only, and anti-stub scope check
    scope_errors: list[str] = []
    for rel, expected_sha in READONLY_SHA256.items():
        if sha256_file(pkg_dir / rel) != expected_sha:
            scope_errors.append(f"read-only file {rel} was modified")

    for rel, (source, tree) in sorted(parsed_files.items()):
        bad_imports = find_non_stdlib_imports(
            tree,
            allowed_packages={PACKAGE_NAME},
            allow_relative=True,
        )
        if bad_imports:
            scope_errors.append(f"{rel}: non-stdlib imports {', '.join(bad_imports)}")
        if rel not in READONLY_SHA256:
            for issue in find_stub_or_placeholder_issues(source, tree):
                scope_errors.append(f"{rel}: {issue}")

    checks.append(
        make_check(
            "readonly_and_scope",
            not scope_errors,
            "tests/test_basic.py untouched, stdlib-only, zero stubs"
            if not scope_errors
            else "; ".join(scope_errors),
        )
    )

    state_errors: list[str] = []
    concurrency_errors: list[str] = []
    removal_errors: list[str] = []

    try:
        with load_candidate_package(pkg_dir.parent, PACKAGE_NAME):
            mod = importlib.import_module(PACKAGE_NAME)
            DuplicateJobError = mod.DuplicateJobError
            LeaseExpiredError = mod.LeaseExpiredError
            JobStatus = mod.JobStatus
            JobScheduler = mod.JobScheduler
            InMemoryJobStore = mod.InMemoryJobStore
            Worker = mod.Worker

            # --- 2a. Priority tie-breaking (FIFO) without TypeError ---
            try:
                now = [0.0]
                sched = JobScheduler(clock=lambda: now[0])
                ids = [sched.submit({"n": i}, priority=5).job_id for i in range(4)]
                claimed_ids = []
                for _ in range(4):
                    j = sched.claim("w1")
                    if j is None:
                        break
                    claimed_ids.append(j.job_id)
                if claimed_ids != ids:
                    state_errors.append(f"equal-priority FIFO mismatch: got {claimed_ids}, expected {ids}")
            except Exception as exc:
                state_errors.append(f"priority-tie test raised {type(exc).__name__}: {exc}")

            # --- 2b. Delayed RETRY_WAIT must not block ready lower-priority job ---
            try:
                now = [0.0]
                sched = JobScheduler(clock=lambda: now[0], retry_delay=10.0)
                j_hi = sched.submit({"k": "hi"}, priority=1, max_attempts=3)
                c1 = sched.claim("w1")
                if c1 is None or c1.job_id != j_hi.job_id:
                    state_errors.append("failed to claim high-priority job")
                else:
                    sched.fail(j_hi.job_id, "w1", "transient", retry_delay=10.0)
                    now[0] = 1.0
                    j_lo = sched.submit({"k": "lo"}, priority=5, max_attempts=2)
                    now[0] = 2.0
                    c_lo = sched.claim("w2")
                    if c_lo is None or c_lo.job_id != j_lo.job_id:
                        state_errors.append(
                            f"delayed RETRY_WAIT blocked ready lower-priority job at t=2.0: got {getattr(c_lo, 'job_id', None)}"
                        )
                    else:
                        sched.complete(c_lo.job_id, "w2", "ok")
                    now[0] = 10.0
                    c_retry = sched.claim("w1")
                    if c_retry is None or c_retry.job_id != j_hi.job_id:
                        state_errors.append("delayed RETRY_WAIT job was not claimable once available_at arrived")
            except Exception as exc:
                state_errors.append(f"delayed-retry test raised {type(exc).__name__}: {exc}")

            # --- 2c. Exact max_attempts, metrics accuracy (no double count), and dedupe release on DEAD_LETTER ---
            try:
                now = [0.0]
                sched = JobScheduler(clock=lambda: now[0], retry_delay=1.0)
                j = sched.submit({"k": "flaky"}, dedupe_key="dk-1", max_attempts=2)

                # Attempt 1 fails -> RETRY_WAIT
                c1 = sched.claim("w1")
                if c1 is None or c1.attempts != 1:
                    state_errors.append(f"attempt 1 mismatch: {c1}")
                sched.fail(j.job_id, "w1", "err-1", retry_delay=1.0)
                if sched.get_job(j.job_id).status != JobStatus.RETRY_WAIT:
                    state_errors.append(f"expected RETRY_WAIT after attempt 1/2, got {sched.get_job(j.job_id).status}")
                snap1 = sched.metrics.snapshot()
                if snap1["retried"] != 1 or snap1["dead_lettered"] != 0:
                    state_errors.append(f"metrics after attempt 1 wrong (double-count?): {snap1}")

                # Active RETRY_WAIT still blocks dedupe_key
                try:
                    sched.submit({"k": "dup"}, dedupe_key="dk-1")
                    state_errors.append("dedupe_key allowed duplicate while job was in RETRY_WAIT")
                except DuplicateJobError:
                    pass

                # Attempt 2 fails -> DEAD_LETTER (not a 3rd attempt!)
                now[0] = 2.0
                c2 = sched.claim("w1")
                if c2 is None or c2.attempts != 2:
                    state_errors.append(f"attempt 2 mismatch: {c2}")
                sched.fail(j.job_id, "w1", "err-2", retry_delay=1.0)
                j_after = sched.get_job(j.job_id)
                if j_after.status != JobStatus.DEAD_LETTER or j_after.attempts != 2:
                    state_errors.append(
                        f"max_attempts=2 off-by-one: status={j_after.status}, attempts={j_after.attempts}"
                    )
                snap2 = sched.metrics.snapshot()
                if snap2["retried"] != 1 or snap2["dead_lettered"] != 1:
                    state_errors.append(f"metrics after dead-letter wrong: {snap2}")

                now[0] = 100.0
                if sched.claim("w1") is not None:
                    state_errors.append("dead-lettered job was claimed a 3rd time")

                # Dedupe key MUST be released after DEAD_LETTER
                j_re = sched.submit({"k": "retry-after-dlq"}, dedupe_key="dk-1", max_attempts=1)
                c_re = sched.claim("w1")
                if c_re is None or c_re.job_id != j_re.job_id:
                    state_errors.append("could not claim re-submitted job after prior DEAD_LETTER")
                sched.complete(j_re.job_id, "w1", "done")
                # SUCCEEDED must still block dedupe_key
                try:
                    sched.submit({"k": "dup-after-success"}, dedupe_key="dk-1")
                    state_errors.append("dedupe_key allowed duplicate after SUCCEEDED")
                except DuplicateJobError:
                    pass
            except Exception as exc:
                state_errors.append(f"max_attempts/dedupe test raised {type(exc).__name__}: {exc}")

            # --- 2d. Lease expiry reclaim + fencing (stale ack/nack -> LeaseExpiredError) ---
            try:
                now = [0.0]
                sched = JobScheduler(clock=lambda: now[0], default_lease_ttl=5.0)
                j = sched.submit({"k": "lease"}, max_attempts=2)
                c1 = sched.claim("w1")
                if c1 is None or c1.lease_owner != "w1":
                    state_errors.append("initial lease claim failed")

                # Advance to exact expiry; w1's own ack must fail with LeaseExpiredError
                now[0] = 5.0
                try:
                    sched.complete(j.job_id, "w1", "too-late")
                    state_errors.append("ack after lease expiry did not raise LeaseExpiredError")
                except LeaseExpiredError:
                    pass

                # w2 claims -> automatically reclaims expired lease and increments expired_requeued
                c2 = sched.claim("w2")
                if c2 is None or c2.job_id != j.job_id or c2.lease_owner != "w2" or c2.attempts != 2:
                    state_errors.append(f"expired lease was not reclaimed by w2: {c2}")
                if sched.metrics.snapshot()["expired_requeued"] != 1:
                    state_errors.append(
                        f"expected expired_requeued == 1, got {sched.metrics.snapshot()['expired_requeued']}"
                    )

                # Stale w1 cannot complete or fail w2's active lease
                for action_name, fn_call in (
                    ("complete", lambda: sched.complete(j.job_id, "w1", "hijack")),
                    ("fail", lambda: sched.fail(j.job_id, "w1", "hijack")),
                ):
                    try:
                        fn_call()
                        state_errors.append(f"stale worker {action_name} did not raise LeaseExpiredError")
                    except LeaseExpiredError:
                        pass

                # Let w2's lease expire at attempts == max_attempts (2) -> must dead-letter!
                now[0] = 10.0
                if sched.claim("w3") is not None:
                    state_errors.append("job with expired lease at max_attempts was re-claimed instead of dead-lettered")
                j_final = sched.get_job(j.job_id)
                if j_final.status != JobStatus.DEAD_LETTER:
                    state_errors.append(f"expired lease at max_attempts status={j_final.status}, expected DEAD_LETTER")
                if sched.metrics.snapshot()["dead_lettered"] != 1:
                    state_errors.append(f"expected dead_lettered == 1 after final lease expiry, got {sched.metrics.snapshot()}")
            except Exception as exc:
                state_errors.append(f"lease-expiry test raised {type(exc).__name__}: {exc}")

            # --- 2e. Worker exception handling (never leaves job stranded in RUNNING) ---
            try:
                now = [0.0]
                sched = JobScheduler(clock=lambda: now[0], retry_delay=2.0)
                j = sched.submit({"k": "boom"}, max_attempts=2)

                def _explode(_job: Any) -> Any:
                    raise RuntimeError("handler exploded")

                worker = Worker("w-err", sched, _explode)
                ran = worker.run_once()
                if ran is not True:
                    state_errors.append(f"Worker.run_once returned {ran!r} after claiming crashing job, expected True")
                j_after = sched.get_job(j.job_id)
                if j_after.status != JobStatus.RETRY_WAIT or "handler exploded" not in (j_after.last_error or ""):
                    state_errors.append(
                        f"Worker crash left job in {j_after.status} (last_error={j_after.last_error!r}), expected RETRY_WAIT"
                    )
                if sched.metrics.snapshot()["retried"] != 1:
                    state_errors.append(f"Worker crash metrics mismatch: {sched.metrics.snapshot()}")
            except Exception as exc:
                state_errors.append(f"Worker exception test raised {type(exc).__name__}: {exc}")

            # --- 2f. Input validation ---
            try:
                sched = JobScheduler(clock=lambda: 0.0)
                bad_calls = [
                    ("max_attempts=0", lambda: sched.submit({}, max_attempts=0)),
                    ("max_attempts=-1", lambda: sched.submit({}, max_attempts=-1)),
                    ("max_attempts=True", lambda: sched.submit({}, max_attempts=True)),
                    ("priority=True", lambda: sched.submit({}, priority=True)),
                    ("lease_ttl=0", lambda: sched.claim("w1", lease_ttl=0)),
                    ("lease_ttl=-5", lambda: sched.claim("w1", lease_ttl=-5)),
                ]
                for label, call in bad_calls:
                    try:
                        call()
                    except ValueError:
                        pass
                    else:
                        state_errors.append(f"invalid argument ({label}) did not raise ValueError")
            except Exception as exc:
                state_errors.append(f"validation test raised {type(exc).__name__}: {exc}")

            # --- 2g. Stage 2 cancel(job_id) -> bool ---
            if stage == 2:
                try:
                    now = [0.0]
                    sched = JobScheduler(clock=lambda: now[0], retry_delay=5.0)
                    if not callable(getattr(sched, "cancel", None)) or not callable(getattr(sched.store, "cancel", None)):
                        state_errors.append("Stage 2 requires cancel(job_id) on both JobScheduler and InMemoryJobStore")
                    else:
                        # Cancel QUEUED job
                        jq = sched.submit({"a": 1}, dedupe_key="cancel-q")
                        if sched.cancel(jq.job_id) is not True:
                            state_errors.append("cancel() on QUEUED job returned False")
                        if sched.get_job(jq.job_id).status != JobStatus.CANCELLED:
                            state_errors.append("cancelled QUEUED job did not transition to CANCELLED")
                        if sched.cancel(jq.job_id) is not False:
                            state_errors.append("second cancel() on already-CANCELLED job returned True")
                        # Claiming must skip cancelled job
                        if sched.claim("w1") is not None:
                            state_errors.append("claim() returned a CANCELLED job")
                        # Dedupe key released on cancel
                        jq2 = sched.submit({"a": 2}, dedupe_key="cancel-q")
                        c_q2 = sched.claim("w1")
                        if c_q2 is None or c_q2.job_id != jq2.job_id:
                            state_errors.append("re-submitted job after CANCELLED could not be claimed")
                        # Cancel RUNNING job must return False and leave RUNNING
                        if sched.cancel(jq2.job_id) is not False:
                            state_errors.append("cancel() on RUNNING job returned True")
                        if sched.get_job(jq2.job_id).status != JobStatus.RUNNING:
                            state_errors.append("cancel() altered RUNNING job status")
                        sched.complete(jq2.job_id, "w1", "ok")
                        if sched.cancel(jq2.job_id) is not False:
                            state_errors.append("cancel() on SUCCEEDED job returned True")

                        # Cancel RETRY_WAIT job
                        jr = sched.submit({"r": 1}, dedupe_key="cancel-r", max_attempts=3)
                        sched.claim("w1")
                        sched.fail(jr.job_id, "w1", "boom", retry_delay=5.0)
                        if sched.cancel(jr.job_id) is not True:
                            state_errors.append("cancel() on RETRY_WAIT job returned False")
                        if sched.get_job(jr.job_id).status != JobStatus.CANCELLED:
                            state_errors.append("cancelled RETRY_WAIT job did not transition to CANCELLED")
                        now[0] = 10.0
                        if sched.claim("w1") is not None:
                            state_errors.append("claim() returned a cancelled RETRY_WAIT job after available_at")
                        # Unknown job returns False
                        if sched.cancel("nonexistent-id") is not False:
                            state_errors.append("cancel() on unknown job_id returned True")
                        # Cancelled metric exact (2 cancelled: jq and jr)
                        if sched.metrics.snapshot()["cancelled"] != 2:
                            state_errors.append(
                                f"expected cancelled metric == 2, got {sched.metrics.snapshot()['cancelled']}"
                            )
                except Exception as exc:
                    state_errors.append(f"Stage 2 cancel test raised {type(exc).__name__}: {exc}")

            # --- 3. Multi-threaded concurrency safety ---
            try:
                now = [0.0]
                sched = JobScheduler(clock=lambda: now[0], retry_delay=0.0)
                total_jobs = 80
                expected_ids = {
                    sched.submit({"i": i}, priority=i % 3).job_id
                    for i in range(total_jobs)
                }
                num_threads = 10
                barrier = threading.Barrier(num_threads)
                claimed_lists: list[list[str]] = [[] for _ in range(num_threads)]
                thread_errs: list[str] = []

                def _claim_worker(idx: int) -> None:
                    try:
                        barrier.wait(timeout=5.0)
                        while True:
                            job = sched.claim(f"wt-{idx}")
                            if job is None:
                                break
                            claimed_lists[idx].append(job.job_id)
                            sched.complete(job.job_id, f"wt-{idx}", idx)
                    except Exception as exc:
                        thread_errs.append(f"worker-{idx}: {type(exc).__name__}: {exc}")

                threads = [threading.Thread(target=_claim_worker, args=(i,)) for i in range(num_threads)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=10.0)
                    if t.is_alive():
                        concurrency_errors.append("worker thread deadlocked during concurrent claim test")

                if thread_errs:
                    concurrency_errors.extend(thread_errs[:5])
                flat = [jid for sub in claimed_lists for jid in sub]
                if len(flat) != len(set(flat)):
                    concurrency_errors.append(
                        f"duplicate claim race detected: {len(flat)} claims for {len(set(flat))} unique jobs"
                    )
                if set(flat) != expected_ids:
                    concurrency_errors.append(
                        f"lost/extra jobs in concurrent claim: got {len(set(flat))}, expected {len(expected_ids)}"
                    )
                snap = sched.metrics.snapshot()
                if snap["enqueued"] != total_jobs or snap["claimed"] != total_jobs or snap["succeeded"] != total_jobs:
                    concurrency_errors.append(f"concurrent metrics drift: {snap}")

                # Concurrent submit with contending dedupe keys
                sched2 = JobScheduler(clock=lambda: 0.0)
                barrier2 = threading.Barrier(8)
                winners: list[int] = [0] * 8
                race_errs: list[str] = []

                def _dedupe_racer(idx: int) -> None:
                    try:
                        barrier2.wait(timeout=5.0)
                        for k in range(25):
                            try:
                                sched2.submit({"t": idx, "k": k}, dedupe_key=f"shared-{k}")
                                winners[idx] += 1
                            except DuplicateJobError:
                                pass
                    except Exception as exc:
                        race_errs.append(f"racer-{idx}: {type(exc).__name__}: {exc}")

                t2 = [threading.Thread(target=_dedupe_racer, args=(i,)) for i in range(8)]
                for t in t2:
                    t.start()
                for t in t2:
                    t.join(timeout=10.0)
                if race_errs:
                    concurrency_errors.extend(race_errs[:5])
                if sum(winners) != 25 or sched2.metrics.snapshot()["enqueued"] != 25:
                    concurrency_errors.append(
                        f"concurrent dedupe race allowed {sum(winners)} winners (metrics={sched2.metrics.snapshot()['enqueued']}), expected 25"
                    )
            except Exception as exc:
                concurrency_errors.append(f"concurrency harness failed: {type(exc).__name__}: {exc}")

            # --- 4. Stage 2 subtractive removal of allow_duplicate_running ---
            if stage == 2:
                for label, fn in (
                    ("InMemoryJobStore.claim_next", InMemoryJobStore.claim_next),
                    ("JobScheduler.claim", JobScheduler.claim),
                ):
                    sig = inspect.signature(fn)
                    if "allow_duplicate_running" in sig.parameters:
                        removal_errors.append(f"{label} still accepts allow_duplicate_running")
                    for p in sig.parameters.values():
                        if p.kind == inspect.Parameter.VAR_KEYWORD:
                            removal_errors.append(f"{label} retains **kwargs compatibility shim")

                sched_rm = JobScheduler(clock=lambda: 0.0)
                try:
                    sched_rm.claim("w1", allow_duplicate_running=False)
                except TypeError:
                    pass
                else:
                    removal_errors.append("JobScheduler.claim(..., allow_duplicate_running=False) did not raise TypeError")

                try:
                    sched_rm.store.claim_next("w1", 0.0, 10.0, allow_duplicate_running=False)
                except TypeError:
                    pass
                else:
                    removal_errors.append("InMemoryJobStore.claim_next(..., allow_duplicate_running=False) did not raise TypeError")

                for rel, (_src, tree) in sorted(parsed_files.items()):
                    if _has_ident_ref(tree, "allow_duplicate_running"):
                        removal_errors.append(f"{rel} still references allow_duplicate_running")
    except Exception as exc:
        state_errors.append(f"runtime load/execution failed: {type(exc).__name__}: {exc}")

    checks.append(
        make_check(
            "state_machine_and_metrics",
            not state_errors,
            "priority ties, delayed retries, max_attempts, dedupe lifecycle, lease fencing, worker crashes, metrics, and cancel passed"
            if not state_errors
            else "; ".join(state_errors),
        )
    )
    checks.append(
        make_check(
            "concurrency_safety",
            not concurrency_errors,
            "concurrent claims, dedupe contention, and metrics passed with zero races or leaks"
            if not concurrency_errors
            else "; ".join(concurrency_errors),
        )
    )
    if stage == 2:
        checks.append(
            make_check(
                "subtractive_removal",
                not removal_errors,
                "allow_duplicate_running removed cleanly across store, scheduler, and worker without **kwargs shims"
                if not removal_errors
                else "; ".join(removal_errors),
            )
        )

    return build_report(CASE_ID, checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grade a candidate m2_jobqueue workspace for case M2.")
    parser.add_argument("workspace", type=Path, help="Path to workspace root or m2_jobqueue package directory")
    parser.add_argument("--stage", type=int, choices=(1, 2), default=2, help="Lineage stage to grade (default: 2)")
    args = parser.parse_args(argv)
    return emit_report(grade(args.workspace, stage=args.stage))


if __name__ == "__main__":
    raise SystemExit(main())
