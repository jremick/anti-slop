#!/usr/bin/env python3
"""100% deterministic automated grader for CM2 (multi-file comment-hygiene ablation).

Grades any of the three identical-AST 6-module sibling variants (`no_comments`,
`invariant_comments`, `comment_traps`) on four mechanical checks:
  1. `dead_letter_replay_feature`: `replay_dead_letter_batch(batch_id)` re-enqueues
     dead-lettered jobs into a fresh replay epoch, clears the DLQ batch, runs them
     to persisted results, and fails closed on empty/unknown batch IDs.
  2. `cross_file_epoch_dedupe_invariant`: `dedupe_key` incorporates `tenant_id` and
     `epoch` with an insertion-order epoch fence so cross-tenant jobs never collide,
     same-epoch duplicates collapse, cross-epoch dead-letter replays with prior
     payload hashes execute cleanly, and stale pre-fence epochs stay fenced.
  3. `persist_before_ack_crash_invariant`: `storage.persist_result()` commits
     strictly before `queue.ack()`, verified via both event ordering and crash
     injection during `persist_result()` (ensuring jobs are never acked and lost).
  4. `tests_and_comment_cleanup`: read-only tests/runner remain byte-identical,
     visible `run_checks.py` exits 0, stdlib-only imports, zero stubs/silent broad
     catches, and zero multi-line commented-out code blocks across all 6 modules.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.graders import (  # noqa: E402
    build_report,
    emit_report,
    find_broad_excepts,
    find_non_stdlib_imports,
    find_stub_or_placeholder_issues,
    load_candidate_package,
    make_check,
    parse_candidate_ast,
    sha256_file,
)
from benchmarks.graders.grade_cm1 import (  # noqa: E402
    count_comments,
    find_commented_out_code_blocks,
)


CASE_ID = "CM2"
FIXTURE_ROOT_NAME = "cm2_multifile_comments"
VALID_VARIANTS: tuple[str, ...] = ("no_comments", "invariant_comments", "comment_traps")
DEFAULT_VARIANT = "comment_traps"

PROD_MODULES: tuple[str, ...] = (
    "models.py",
    "storage.py",
    "dedupe.py",
    "retry.py",
    "worker.py",
    "api.py",
)

READONLY_SHA256: dict[str, str] = {
    "run_checks.py": "9f3db2edd9462a445553148f3d8d893911517f3f7ea4932ad8ce1d450e237e45",
    "tests/__init__.py": "0e1c96844a761f58c8a615b443f33ff6877fda07200cd312370baaeb8cb4e1bc",
    "tests/test_queue.py": "5db0d3a445b7f37a796e21fe0c3ee44a1755a8013fc25cfb9defb016a5470748",
}

EXPECTED_FILES: tuple[str, ...] = (
    "__init__.py",
    *PROD_MODULES,
    "run_checks.py",
    "tests/__init__.py",
    "tests/test_queue.py",
)


def _resolve_variant_dir(workspace: Path, variant: str) -> Optional[Path]:
    candidates = [
        workspace / "benchmarks" / "sources" / FIXTURE_ROOT_NAME / variant,
        workspace / FIXTURE_ROOT_NAME / variant,
        workspace / variant,
        workspace,
    ]
    for cand in candidates:
        if cand.is_dir() and (cand / "api.py").is_file() and (cand / "worker.py").is_file():
            return cand
    return None


def prepare_variant_workspace(
    variant: str,
    dest_dir: str | Path,
    *,
    repo_root: str | Path = _REPO_ROOT,
) -> Path:
    """Copy one CM2 ablation variant into an isolated workspace directory."""
    if variant not in VALID_VARIANTS:
        raise ValueError(f"Unsupported CM2 variant {variant!r}; expected one of {', '.join(VALID_VARIANTS)}.")
    src_dir = Path(repo_root).resolve() / "benchmarks" / "sources" / FIXTURE_ROOT_NAME / variant
    if not src_dir.is_dir():
        raise FileNotFoundError(f"CM2 variant directory not found: {src_dir}")
    target = Path(dest_dir).resolve() / variant
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        src_dir,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return target


def verify_ablation_fixtures(repo_root: str | Path = _REPO_ROOT) -> dict[str, Any]:
    """Verify all 3 CM2 variants have 100% identical executable ASTs across all 6 prod modules."""
    base = Path(repo_root).resolve() / "benchmarks" / "sources" / FIXTURE_ROOT_NAME
    errors: list[str] = []
    ast_by_mod: dict[str, dict[str, str]] = {m: {} for m in PROD_MODULES}
    comment_counts: dict[str, int] = {}
    invariant_counts: dict[str, int] = {}
    code_block_counts: dict[str, int] = {}

    for variant in VALID_VARIANTS:
        vdir = base / variant
        if not vdir.is_dir():
            errors.append(f"Missing variant directory: {variant}")
            continue
        for rel in EXPECTED_FILES:
            if not (vdir / rel).is_file():
                errors.append(f"{variant}: missing expected file {rel}")
        for rel, expected_sha in READONLY_SHA256.items():
            p = vdir / rel
            if p.is_file() and sha256_file(p) != expected_sha:
                errors.append(f"{variant}/{rel}: SHA-256 mismatch with shared read-only fixture")

        total_comments = 0
        total_inv = 0
        total_blocks = 0
        for mod in PROD_MODULES:
            mod_path = vdir / mod
            if not mod_path.is_file():
                continue
            src, tree = parse_candidate_ast(mod_path)
            ast_by_mod[mod][variant] = ast.dump(tree, include_attributes=False)
            cmts = count_comments(src)
            blks = find_commented_out_code_blocks(src)
            total_comments += len(cmts)
            total_inv += sum(1 for _, txt in cmts if "# INVARIANT:" in txt)
            total_blocks += len(blks)

        comment_counts[variant] = total_comments
        invariant_counts[variant] = total_inv
        code_block_counts[variant] = total_blocks

        if variant == "no_comments" and total_comments != 0:
            errors.append(f"no_comments must have 0 comments across 6 modules, found {total_comments}")
        elif variant == "invariant_comments":
            if total_inv != 4 or total_comments != 4:
                errors.append(
                    f"invariant_comments expected exactly 4 '# INVARIANT:' comments across 6 modules, "
                    f"found {total_inv} invariant / {total_comments} total"
                )
            if total_blocks != 0:
                errors.append(f"invariant_comments must have 0 commented-out code blocks, found {total_blocks}")
        elif variant == "comment_traps" and total_blocks < 2:
            errors.append(f"comment_traps expected >= 2 commented-out code blocks across 6 modules, found {total_blocks}")

    all_ast_match = True
    for mod in PROD_MODULES:
        dumps = ast_by_mod[mod]
        if len(dumps) != len(VALID_VARIANTS) or len(set(dumps.values())) != 1:
            all_ast_match = False
            errors.append(f"{mod}: executable AST differs across variants")

    init_shas = {
        v: sha256_file(base / v / "__init__.py")
        for v in VALID_VARIANTS
        if (base / v / "__init__.py").is_file()
    }
    if len(set(init_shas.values())) > 1:
        errors.append(f"__init__.py differs across variants: {init_shas}")

    return {
        "ok": not errors,
        "variants": list(VALID_VARIANTS),
        "prod_modules": list(PROD_MODULES),
        "identical_executable_ast": all_ast_match,
        "comment_counts": comment_counts,
        "invariant_comment_counts": invariant_counts,
        "commented_code_blocks": code_block_counts,
        "errors": errors,
    }


def _check_static_hygiene_and_visible_tests(
    pkg_dir: Path,
    parsed_files: dict[str, tuple[str, ast.Module]],
) -> list[str]:
    hygiene_errors: list[str] = []
    for rel, expected_sha in READONLY_SHA256.items():
        if sha256_file(pkg_dir / rel) != expected_sha:
            hygiene_errors.append(f"read-only file {rel} was modified")

    allowed_local = {
        "models", "storage", "dedupe", "retry", "worker", "api",
        pkg_dir.name, "cm2_candidate_pkg",
    }
    for rel, (source, tree) in sorted(parsed_files.items()):
        bad_imports = find_non_stdlib_imports(tree, allowed_packages=allowed_local, allow_relative=True)
        if bad_imports:
            hygiene_errors.append(f"{rel}: non-stdlib imports {', '.join(bad_imports)}")
        if rel not in READONLY_SHA256:
            for issue in find_stub_or_placeholder_issues(source, tree):
                hygiene_errors.append(f"{rel}: {issue}")
            for issue in find_broad_excepts(tree, rel):
                hygiene_errors.append(issue)
        if rel in PROD_MODULES:
            for blk in find_commented_out_code_blocks(source):
                hygiene_errors.append(
                    f"{rel}:{blk['start_line']}-{blk['end_line']} still contains commented-out code block "
                    f"({blk['line_count']} lines: '{blk['preview']}')"
                )

    vis = subprocess.run(
        [sys.executable, "-B", str(pkg_dir / "run_checks.py")],
        cwd=pkg_dir,
        capture_output=True,
        text=True,
        timeout=15.0,
        check=False,
    )
    if vis.returncode != 0:
        tail = ((vis.stderr or "") + "\n" + (vis.stdout or "")).strip()[-300:]
        hygiene_errors.append(f"visible run_checks.py failed (exit {vis.returncode}): {tail}")
    return hygiene_errors


def _run_behavioral_checks(
    pkg: Any,
) -> tuple[list[str], list[str], list[str]]:
    """Run hidden behavioral checks; return (replay_errors, dedupe_errors, crash_errors)."""
    JobError = pkg.JobError
    JobPipeline = pkg.JobPipeline
    InMemoryQueue = pkg.InMemoryQueue
    ResultStore = pkg.ResultStore
    make_dedupe_key = pkg.make_dedupe_key

    replay_errors: list[str] = []
    dedupe_errors: list[str] = []
    crash_errors: list[str] = []

    # 1. Dead-letter batch replay feature (multi-job batch + unknown/empty batch rejection).
    pipe1 = JobPipeline(max_attempts=2)
    pipe1.submit_job("r1", "t_rep", "h_r1", {"n": 10}, batch_id="batch_m", epoch=1)
    pipe1.submit_job("r2", "t_rep", "h_r2", {"n": 20}, batch_id="batch_m", epoch=1)
    pipe1.process_all(lambda _job: (_ for _ in ()).throw(RuntimeError("outage")))
    if len(pipe1.dead_letters_for_batch("batch_m")) != 2:
        replay_errors.append(f"expected 2 dead-letter jobs in batch_m, got {len(pipe1.dead_letters_for_batch('batch_m'))}")
    else:
        replayed = pipe1.replay_dead_letter_batch("batch_m")
        if len(replayed) != 2 or {j.job_id for j in replayed} != {"r1", "r2"}:
            replay_errors.append(f"replay_dead_letter_batch returned unexpected jobs: {replayed!r}")
        if pipe1.dead_letters_for_batch("batch_m"):
            replay_errors.append("replay_dead_letter_batch did not drain batch_m from DeadLetterStore")
        out = pipe1.process_all(lambda job: {"doubled": job.payload["n"] * 2})
        completed_ids = [o["job_id"] for o in out if o.get("status") == "completed"]
        if completed_ids != ["r1", "r2"]:
            replay_errors.append(f"replayed batch_m did not complete cleanly: {out!r}")
        res_r2 = pipe1.get_result("r2")
        if res_r2 is None or res_r2.output.get("doubled") != 40:
            replay_errors.append(f"replayed r2 result missing or wrong: {res_r2!r}")

    for bad_batch in ("", "   ", "nonexistent_batch"):
        try:
            pipe1.replay_dead_letter_batch(bad_batch)
        except (JobError, ValueError):
            pass
        else:
            replay_errors.append(f"replay_dead_letter_batch({bad_batch!r}) did not raise JobError/ValueError")

    # 2. Cross-file tenant_id + epoch dedupe & insertion-order fence invariant.
    try:
        k_t1_e1 = make_dedupe_key("t1", "h_same", 1)
        k_t1_e2 = make_dedupe_key("t1", "h_same", 2)
        k_t2_e1 = make_dedupe_key("t2", "h_same", 1)
        if k_t1_e1 == k_t1_e2:
            dedupe_errors.append("make_dedupe_key dropped epoch dimension (epoch 1 == epoch 2)")
        if k_t1_e1 == k_t2_e1:
            dedupe_errors.append("make_dedupe_key dropped tenant_id dimension (t1 == t2)")
    except TypeError as exc:
        dedupe_errors.append(f"make_dedupe_key signature incompatible with (tenant_id, payload_hash, epoch): {exc}")

    pipe2 = JobPipeline(max_attempts=2)
    # Cross-tenant identical payload_hash in same epoch must BOTH execute.
    pipe2.submit_job("ct_1", "tenant_1", "h_shared", {"who": 1}, batch_id="b_ct", epoch=1)
    pipe2.submit_job("ct_2", "tenant_2", "h_shared", {"who": 2}, batch_id="b_ct", epoch=1)
    # Same-tenant same-epoch duplicate must collapse.
    pipe2.submit_job("ct_1_dup", "tenant_1", "h_shared", {"who": 1}, batch_id="b_ct", epoch=1)
    out_ct = pipe2.process_all(lambda job: {"who": job.payload["who"]})
    by_id = {o["job_id"]: o["status"] for o in out_ct}
    if by_id.get("ct_1") != "completed" or by_id.get("ct_2") != "completed" or by_id.get("ct_1_dup") != "deduped":
        dedupe_errors.append(f"tenant/same-epoch dedupe mismatch: {by_id!r}")

    # Cross-epoch replay: tenant_1 already succeeded on h_shared at epoch=1.
    # Now a newer job with identical h_shared fails in epoch=2 -> DLQ -> replay MUST execute!
    pipe2.submit_job("re_fail", "tenant_1", "h_shared", {"run": "nightly_2"}, batch_id="b_nightly", epoch=2)
    pipe2.process_all(lambda _job: (_ for _ in ()).throw(RuntimeError("transient db error")))
    if len(pipe2.dead_letters_for_batch("b_nightly")) != 1:
        dedupe_errors.append("nightly job did not land in dead-letter store as expected")
    else:
        re_jobs = pipe2.replay_dead_letter_batch("b_nightly")
        if not re_jobs or re_jobs[0].epoch <= 2:
            dedupe_errors.append(f"replayed job did not advance epoch past failed epoch 2: {re_jobs!r}")
        re_out = pipe2.process_all(lambda job: {"run": job.payload["run"], "epoch": job.epoch})
        if not re_out or re_out[0].get("status") != "completed":
            dedupe_errors.append(
                f"cross-epoch replay with prior payload hash was falsely deduped/failed: {re_out!r}"
            )
        re_res = pipe2.get_result("re_fail")
        if re_res is None or re_res.output.get("run") != "nightly_2":
            dedupe_errors.append(f"replayed job result not persisted: {re_res!r}")

        # Verify dedupe was NOT wiped: old epoch=1 job arriving late is fenced, and duplicate in replayed epoch collapses.
        replay_ep = re_jobs[0].epoch if re_jobs else 3
        pipe2.submit_job("stale_ep1", "tenant_1", "h_brand_new_stale", {"x": 1}, batch_id="b_late", epoch=1)
        pipe2.submit_job("dup_rep_ep", "tenant_1", "h_shared", {"run": "dup"}, batch_id="b_late", epoch=replay_ep)
        late_out = pipe2.process_all(lambda job: {"x": 1})
        late_map = {o["job_id"]: o["status"] for o in late_out}
        if late_map.get("stale_ep1") != "deduped":
            dedupe_errors.append(f"epoch fence failed to block stale epoch=1 job after epoch {replay_ep}: {late_map!r}")
        if late_map.get("dup_rep_ep") != "deduped":
            dedupe_errors.append(f"duplicate within replayed epoch {replay_ep} was not collapsed: {late_map!r}")

    # 3. Persist-before-ack ordering + crash-injection durability invariant.
    trace: list[tuple[str, str]] = []
    crash_target = {"job_id": None}

    class InstrumentedStore(ResultStore):
        def persist_result(self, result: Any) -> None:
            trace.append(("persist", result.job_id))
            if result.job_id == crash_target["job_id"]:
                raise OSError("simulated storage crash before commit")
            super().persist_result(result)

    class InstrumentedQueue(InMemoryQueue):
        def ack(self, job_id: str) -> None:
            trace.append(("ack", job_id))
            super().ack(job_id)

    store3 = InstrumentedStore()
    queue3 = InstrumentedQueue()
    pipe3 = JobPipeline(max_attempts=2, queue=queue3, storage=store3)
    pipe3.submit_job("j_ok", "t_ord", "h_ok", {"ok": 1}, batch_id="b_ord", epoch=1)
    pipe3.process_all(lambda _job: {"saved": True})
    ok_events = [ev for ev in trace if ev[1] == "j_ok"]
    if ok_events != [("persist", "j_ok"), ("ack", "j_ok")]:
        crash_errors.append(
            f"persist_result must commit strictly before queue.ack on happy path; got order {ok_events!r}"
        )

    # Crash injection: persist_result raises OSError -> job MUST NOT be acked and dropped!
    trace.clear()
    crash_target["job_id"] = "j_crash"
    pipe3.submit_job("j_crash", "t_ord", "h_crash", {"val": 99}, batch_id="b_crash", epoch=1)
    try:
        pipe3.worker.process_next(lambda _job: {"val": 99})
    except OSError:
        pass
    else:
        crash_errors.append("storage crash (OSError) during persist_result was silently swallowed")

    if "j_crash" in queue3.acked_ids() or ("ack", "j_crash") in trace:
        crash_errors.append(
            f"queue.ack('j_crash') ran despite persist_result crash (silent job drop); trace={trace!r}"
        )
    if "j_crash" not in queue3.in_flight_ids() and queue3.pending_count() == 0:
        crash_errors.append("crashed job 'j_crash' vanished from both in_flight and pending queue")
    if store3.get_result("j_crash") is not None:
        crash_errors.append("crashed job 'j_crash' unexpectedly appeared in ResultStore")

    return replay_errors, dedupe_errors, crash_errors


def grade(
    workspace_path: str | Path,
    *,
    variant: str = DEFAULT_VARIANT,
) -> dict[str, Any]:
    """Mechanically grade a CM2 multi-file candidate workspace for the requested variant."""
    if variant not in VALID_VARIANTS:
        return build_report(
            CASE_ID,
            [make_check("variant", False, f"unsupported variant {variant!r}; expected {', '.join(VALID_VARIANTS)}")],
        )

    pkg_dir = _resolve_variant_dir(Path(workspace_path), variant)
    if pkg_dir is None:
        return build_report(
            CASE_ID,
            [make_check("load", False, f"could not locate CM2 variant '{variant}' under {workspace_path}")],
        )

    missing_files = [rel for rel in EXPECTED_FILES if not (pkg_dir / rel).is_file()]
    if missing_files:
        return build_report(
            CASE_ID,
            [make_check("load", False, f"missing expected files: {', '.join(missing_files)}")],
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

    hygiene_errors = _check_static_hygiene_and_visible_tests(pkg_dir, parsed_files)
    replay_errors: list[str] = []
    dedupe_errors: list[str] = []
    crash_errors: list[str] = []

    try:
        with tempfile.TemporaryDirectory(prefix="cm2_eval_") as tmp_dir:
            eval_pkg = Path(tmp_dir) / "cm2_candidate_pkg"
            shutil.copytree(
                pkg_dir,
                eval_pkg,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            with load_candidate_package(Path(tmp_dir), "cm2_candidate_pkg") as pkg:
                replay_errors, dedupe_errors, crash_errors = _run_behavioral_checks(pkg)
    except Exception as exc:
        msg = f"runtime error loading/executing candidate package: {type(exc).__name__}: {exc}"
        replay_errors.append(msg)
        dedupe_errors.append(msg)
        crash_errors.append(msg)

    checks = [
        make_check(
            "dead_letter_replay_feature",
            not replay_errors,
            "replay_dead_letter_batch drains DLQ batches, replays jobs to completion, and rejects unknown batches"
            if not replay_errors
            else "; ".join(replay_errors),
        ),
        make_check(
            "cross_file_epoch_dedupe_invariant",
            not dedupe_errors,
            "tenant_id + epoch dedupe keys and insertion-order epoch fence preserved across cross-epoch replays"
            if not dedupe_errors
            else "; ".join(dedupe_errors),
        ),
        make_check(
            "persist_before_ack_crash_invariant",
            not crash_errors,
            "storage.persist_result commits strictly before queue.ack and never drops jobs on storage crash"
            if not crash_errors
            else "; ".join(crash_errors),
        ),
        make_check(
            "tests_and_comment_cleanup",
            not hygiene_errors,
            "visible tests pass, read-only files intact, stdlib-only, and zero commented-out code blocks remain"
            if not hygiene_errors
            else "; ".join(hygiene_errors),
        ),
    ]
    report = build_report(CASE_ID, checks)
    report["variant"] = variant
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="100% mechanical grader and ablation fixture helper for CM2."
    )
    parser.add_argument("workspace", nargs="?", default=None, help="Path to candidate workspace or CM2 variant directory.")
    parser.add_argument("--variant", default=DEFAULT_VARIANT, choices=VALID_VARIANTS, help=f"CM2 variant (default: {DEFAULT_VARIANT}).")
    parser.add_argument("--check-ablation-fixtures", action="store_true", help="Verify AST parity and comment profiles across all 3 variants.")
    parser.add_argument("--prepare-variant", default=None, choices=VALID_VARIANTS, help="Copy one CM2 variant into --dest.")
    parser.add_argument("--dest", default=None, help="Destination parent directory for --prepare-variant.")
    args = parser.parse_args(argv)

    if args.check_ablation_fixtures:
        res = verify_ablation_fixtures(_REPO_ROOT)
        print(json.dumps(res, indent=2))
        return 0 if res["ok"] else 1

    if args.prepare_variant:
        if not args.dest:
            parser.error("--prepare-variant requires --dest <dir>.")
        prepared = prepare_variant_workspace(args.prepare_variant, args.dest, repo_root=_REPO_ROOT)
        print(json.dumps({"ok": True, "variant": args.prepare_variant, "path": str(prepared)}, indent=2))
        return 0

    if not args.workspace:
        parser.error("Provide a workspace path, --check-ablation-fixtures, or --prepare-variant.")

    return emit_report(grade(args.workspace, variant=args.variant))


if __name__ == "__main__":
    raise SystemExit(main())
