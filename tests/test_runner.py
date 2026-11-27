"""Focused integrity tests for scripts/run_benchmark.py (no model/network calls)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import benchmark, run_benchmark  # noqa: E402


class RunnerIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_freeze_conditions_pins_v01_and_v02_and_blocks_drift(self) -> None:
        cond_dir = self.root / "conditions"
        # Works even on shallow CI checkouts where git show main:... is unavailable.
        with mock.patch("scripts.run_benchmark._git_show_file", side_effect=AssertionError("should use frozen snapshot")):
            snaps = run_benchmark.freeze_conditions(
                REPO_ROOT, cond_dir, ["baseline", "core-rules-v0.1.0", "core-rules-v0.2.0"]
            )
        v01 = snaps["core-rules-v0.1.0"].read_text(encoding="utf-8")
        v02 = snaps["core-rules-v0.2.0"].read_text(encoding="utf-8")
        self.assertIn("Version 0.1.0.", v01)
        self.assertIn("Version 0.2.0.", v02)
        self.assertNotEqual(v01, v02)
        # Re-freezing with identical content is idempotent.
        run_benchmark.freeze_conditions(REPO_ROOT, cond_dir, ["baseline", "core-rules-v0.2.0"])
        # Mutating a frozen snapshot raises an error instead of silently overwriting.
        snaps["core-rules-v0.2.0"].write_text("tampered\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            run_benchmark.freeze_conditions(REPO_ROOT, cond_dir, ["core-rules-v0.2.0"])

    def test_prepare_clean_workspace_isolates_outside_repo_and_copies_only_case_sources(self) -> None:
        cases = benchmark.load_cases(REPO_ROOT / "benchmarks" / "cases", REPO_ROOT)
        case = cases[("T1", "0.2.0")]
        workdir, hashes = run_benchmark.prepare_clean_workspace(
            REPO_ROOT, case, run_benchmark.BASELINE_INSTRUCTION, write_agents_md=True, run_id="test_iso"
        )
        self.addCleanup(lambda: shutil.rmtree(workdir, ignore_errors=True))
        self.assertFalse(workdir.resolve().is_relative_to(REPO_ROOT.resolve()))
        self.assertEqual(
            set(hashes.keys()),
            {"benchmarks/sources/t1-cache.py", "benchmarks/sources/t1-test-visible.py", "AGENTS.md"},
        )
        self.assertFalse((workdir / "benchmarks/graders").exists())
        self.assertFalse((workdir / "standard/core.md").exists())

    def test_extract_coding_candidate_prefers_symbol_bearing_copy_over_test_script(self) -> None:
        cases = benchmark.load_cases(REPO_ROOT / "benchmarks" / "cases", REPO_ROOT)
        case = cases[("C2", "0.1.0")]
        workdir, hashes = run_benchmark.prepare_clean_workspace(
            REPO_ROOT, case, run_benchmark.BASELINE_INSTRUCTION, write_agents_md=False, run_id="test_extract"
        )
        self.addCleanup(lambda: shutil.rmtree(workdir, ignore_errors=True))
        (workdir / "verify_c2.py").write_text("print('ok')\n", encoding="utf-8")
        (workdir / "c2_solution.py").write_text("def invoice_total(lines):\n    return 0\n", encoding="utf-8")
        dest = self.root / "captured.py"
        path, how = run_benchmark.extract_coding_candidate("C2", workdir, hashes, "", dest)
        self.assertEqual(path, dest)
        self.assertEqual(how, "workspace_created:c2_solution.py")
        self.assertIn("def invoice_total", dest.read_text(encoding="utf-8"))

    def test_parsers_extract_usage_and_flag_fable_downgrade(self) -> None:
        codex_out = "\n".join([
            json.dumps({"type": "thread.started", "thread_id": "thr-123"}),
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "Done"}}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 20}}),
        ])
        cp = run_benchmark.parse_codex_jsonl(codex_out)
        self.assertEqual(cp["session_id"], "thr-123")
        self.assertEqual(cp["text"], "Done")
        self.assertEqual(cp["total_tokens"], 120)

        claude_downgrade = json.dumps({
            "session_id": "sid-9",
            "result": "Refused",
            "is_error": False,
            "total_cost_usd": 0.12,
            "modelUsage": {
                "claude-opus-4-8": {"inputTokens": 50, "outputTokens": 10},
            },
        })
        clp = run_benchmark.parse_claude_json(claude_downgrade)
        self.assertEqual(clp["downgraded_models"], ["claude-opus-4-8"])
        self.assertEqual(clp["total_tokens"], 60)

        agy_log = self.root / "stage.agy.log"
        agy_log.write_text(
            'Propagating selected model override to backend: label="Gemini 4 Neon (High)"\n'
            'Created conversation 11111111-2222-3333-4444-555555555555 (backend=X)\n',
            encoding="utf-8",
        )
        tdir = self.root / "brain" / "11111111-2222-3333-4444-555555555555" / ".system_generated" / "logs"
        tdir.mkdir(parents=True)
        (tdir / "transcript.jsonl").write_text(
            json.dumps({"type": "PLANNER_RESPONSE", "model": "gemini-4-neon-high", "input_tokens": 200, "output_tokens": 30}) + "\n",
            encoding="utf-8",
        )
        ap = run_benchmark.parse_agy_telemetry(agy_log, agy_brain_root=self.root / "brain")
        self.assertEqual(ap["session_id"], "11111111-2222-3333-4444-555555555555")
        self.assertEqual(ap["observed_model"], "gemini-4-neon-high")
        self.assertEqual(ap["total_tokens"], 230)

    def test_dry_run_creates_manifest_and_snapshots_without_calling_models(self) -> None:
        rc = run_benchmark.main([
            "--experiment-id", "dry-smoke",
            "--cases", "C2", "S1", "T1",
            "--output-root", str(self.root / "out"),
            "--dry-run",
        ])
        self.assertEqual(rc, 0)
        manifest = json.loads((self.root / "out" / "dry-smoke" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["cases"], ["C2", "S1", "T1"])
        self.assertEqual(len(manifest["models"]), 5)
        self.assertEqual(set(manifest["conditions"].keys()), {"baseline", "core-rules-v0.1.0", "core-rules-v0.2.0"})

    def test_claude_429_rate_limit_classifies_as_blocked(self) -> None:
        payload = json.dumps({
            "session_id": "sid-429",
            "is_error": True,
            "terminal_reason": "api_error",
            "api_error_status": 429,
            "result": "You've hit your limit (usage_limit_reached)",
            "total_cost_usd": 0.0,
            "modelUsage": {},
        })
        parsed = run_benchmark.parse_claude_json(payload)
        self.assertEqual(parsed["api_error_status"], 429)
        self.assertTrue(parsed["is_rate_limited"])

        workdir = self.root / "wd_claude"
        workdir.mkdir()
        trace = self.root / "art_claude" / "stage-1-trace.log"
        trace.parent.mkdir()
        fake_proc = subprocess.CompletedProcess(args=["claude"], returncode=1, stdout=payload, stderr="")
        with mock.patch("scripts.run_benchmark._run_stage_subprocess", return_value=fake_proc):
            res = run_benchmark._invoke_stage(
                {"cli": "claude", "id": "claude-opus-5-5", "reasoning": "medium"},
                "baseline",
                "hello",
                workdir,
                1,
                None,
                trace,
                30,
            )
        self.assertEqual(res["status"], "blocked")
        self.assertIn("api_error_status=429", res["error"])

    def test_codex_timeout_keeps_out_msg_file_outside_workdir(self) -> None:
        workdir = self.root / "wd_codex"
        workdir.mkdir()
        trace = self.root / "art_codex" / "stage-2-trace.log"
        trace.parent.mkdir()
        captured_cmds: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_cmds.append(cmd)
            out_idx = cmd.index("-o") + 1
            Path(cmd[out_idx]).write_text("", encoding="utf-8")
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=30, output="", stderr="")

        with mock.patch("scripts.run_benchmark._run_stage_subprocess", side_effect=fake_run):
            res = run_benchmark._invoke_stage(
                {"cli": "codex", "id": "gpt-6.2-sol", "reasoning": "medium"},
                "baseline",
                "follow-up",
                workdir,
                2,
                "thr-123",
                trace,
                30,
            )
        self.assertEqual(res["status"], "timeout")
        out_path = Path(captured_cmds[0][captured_cmds[0].index("-o") + 1]).resolve()
        self.assertFalse(out_path.is_relative_to(workdir.resolve()))
        self.assertEqual(list(workdir.iterdir()), [])
        self.assertFalse(out_path.exists())

    def test_freeze_model_controls_isolates_per_model_deltas_and_dry_run_v030(self) -> None:
        cond_dir = self.root / "cond_mc"
        models = ["gpt-6.2-astra", "claude-opus-5-5"]
        snaps = run_benchmark.freeze_conditions(
            REPO_ROOT, cond_dir, ["baseline", "core-rules-v0.2.0", "model-controls"], models=models
        )
        opus_path = run_benchmark.resolve_condition_file(snaps, "model-controls", "claude-opus-5-5")
        astra_path = run_benchmark.resolve_condition_file(snaps, "model-controls", "gpt-6.2-astra")
        opus_txt = opus_path.read_text(encoding="utf-8")
        astra_txt = astra_path.read_text(encoding="utf-8")
        self.assertIn("D-OPU-4:", opus_txt)
        self.assertNotIn("D-AST-1:", opus_txt)
        self.assertIn("D-AST-1:", astra_txt)
        self.assertNotIn("D-OPU-4:", astra_txt)

        rc = run_benchmark.main([
            "--experiment-id", "dry-v030",
            "--cases", "M1", "M2", "B2", "D1", "S2", "W3",
            "--models", "gpt-6.2-astra", "claude-opus-5-5",
            "--conditions", "baseline", "core-rules-v0.2.0", "model-controls",
            "--output-root", str(self.root / "out_v030"),
            "--dry-run",
        ])
        self.assertEqual(rc, 0)
        manifest = json.loads((self.root / "out_v030" / "dry-v030" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["cases"], ["M1", "M2", "B2", "D1", "S2", "W3"])
        self.assertIn("model-controls__claude-opus-5-5", manifest["conditions"])
        self.assertIn("model-controls__gpt-6.2-astra", manifest["conditions"])

    def test_auto_populate_checks_handles_v030_workspace_readonly_and_wordcaps(self) -> None:
        cases = benchmark.load_cases(REPO_ROOT / "benchmarks" / "cases", REPO_ROOT)

        # Read-only violation on S2 flags material defect
        s2_checks, s2_defects = run_benchmark._auto_populate_checks(
            cases[("S2", "0.3.0")],
            {},
            {1: {"modified": ["benchmarks/sources/s2_acl/cache.py"], "created": [], "deleted": []}},
        )
        self.assertEqual(len(s2_defects), 1)
        self.assertIn("S2 read-only violation", s2_defects[0])
        self.assertTrue(all(c["status"] == "not_run" for c in s2_checks))

        # Word-cap + read-only check auto-populates on D1
        d1_pass, d1_defects = run_benchmark._auto_populate_checks(
            cases[("D1", "0.3.0")],
            {},
            {1: {"modified": [], "created": [], "deleted": []}, 2: {"modified": [], "created": [], "deleted": []}},
            {
                1: ({"passed": True, "lexical_words": 110}, "s1.md"),
                2: ({"passed": True, "lexical_words": 65}, "s2.md"),
            },
        )
        self.assertEqual(d1_defects, [])
        d1_map = {c["id"]: c for c in d1_pass}
        self.assertEqual(d1_map["word_caps_and_readonly"]["status"], "pass")
        self.assertEqual(d1_map["word_caps_and_readonly"]["evidence"], ["s1.md", "s2.md"])

        d1_fail, d1_defects_fail = run_benchmark._auto_populate_checks(
            cases[("D1", "0.3.0")],
            {},
            {1: {"modified": [], "created": ["notes.md"], "deleted": []}, 2: {"modified": [], "created": [], "deleted": []}},
            {
                1: ({"passed": True, "lexical_words": 110}, "s1.md"),
                2: ({"passed": False, "lexical_words": 82}, "s2.md"),
            },
        )
        self.assertEqual(len(d1_defects_fail), 1)
        self.assertEqual({c["id"]: c["status"] for c in d1_fail}["word_caps_and_readonly"], "fail")

        # B2 brevity failure marks refusal_and_brevity_signoff fail immediately
        b2_rep1 = {
            "passed": True,
            "checks": [
                {"id": "readonly_and_no_test_tampering", "passed": True, "detail": "ok"},
                {"id": "code_fixes_verified", "passed": True, "detail": "ok"},
                {"id": "fail_closed_preserved", "passed": True, "detail": "ok"},
            ],
        }
        b2_rep2 = {
            "passed": False,
            "checks": [
                {"id": "readonly_and_no_test_tampering", "passed": True, "detail": "ok"},
                {"id": "code_fixes_verified", "passed": True, "detail": "ok"},
                {"id": "fail_closed_preserved", "passed": True, "detail": "ok"},
                {"id": "brevity_and_zero_wrapper", "passed": False, "detail": "95 > 90"},
            ],
        }
        b2_checks, _ = run_benchmark._auto_populate_checks(
            cases[("B2", "0.3.0")],
            {1: (b2_rep1, "g1.json"), 2: (b2_rep2, "g2.json")},
            {},
        )
        b2_map = {c["id"]: c["status"] for c in b2_checks}
        self.assertEqual(b2_map["code_fixes_verified"], "pass")
        self.assertEqual(b2_map["fail_closed_preserved"], "pass")
        self.assertEqual(b2_map["readonly_and_no_test_tampering"], "pass")
        self.assertEqual(b2_map["refusal_and_brevity_signoff"], "fail")

    def test_stage_subprocess_reaps_grandchild_on_timeout(self) -> None:
        pid_file = self.root / "grandchild.pid"
        parent_code = (
            "import pathlib, subprocess, sys, time\n"
            f"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid), encoding='utf-8')\n"
            "time.sleep(60)\n"
        )
        t0 = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            run_benchmark._run_stage_subprocess(
                [sys.executable, "-c", parent_code],
                cwd=self.root,
                env=None,
                timeout_seconds=1.0,
                child_max_rss_mb=0,
            )
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 6.0, "timeout cleanup should not hang on grandchild pipes")
        self.assertTrue(pid_file.is_file(), "grandchild should have spawned before timeout")
        grandchild_pid = int(pid_file.read_text(encoding="utf-8").strip())
        # Allow brief kernel reap delay after SIGKILL.
        deadline = time.monotonic() + 2.0
        alive = True
        while time.monotonic() < deadline:
            try:
                os.kill(grandchild_pid, 0)
                time.sleep(0.05)
            except ProcessLookupError:
                alive = False
                break
        self.assertFalse(alive, f"grandchild pid {grandchild_pid} survived timeout cleanup")

    def test_stage_subprocess_rss_watchdog_kills_runaway_child(self) -> None:
        child_code = (
            "import time\n"
            "buf = bytearray(80 * 1024 * 1024)\n"
            "for i in range(0, len(buf), 4096):\n"
            "    buf[i] = 1\n"
            "time.sleep(30)\n"
        )
        parent_code = (
            "import subprocess, sys\n"
            f"p = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
            "rc = p.wait()\n"
            "print(f'CHILD_RC={rc}', flush=True)\n"
        )
        proc = run_benchmark._run_stage_subprocess(
            [sys.executable, "-c", parent_code],
            cwd=self.root,
            env=None,
            timeout_seconds=15.0,
            child_max_rss_mb=32,
            rss_poll_interval_s=0.15,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("CHILD_RC=-9", proc.stdout)
        self.assertIn("[run_benchmark watchdog] SIGKILL child", proc.stderr)

    def test_cli_validates_max_workers_and_child_max_rss_mb(self) -> None:
        rc = run_benchmark.main([
            "--experiment-id", "dry-limits",
            "--cases", "RW3",
            "--models", "gpt-6.2-astra",
            "--conditions", "baseline",
            "--max-workers", "2",
            "--child-max-rss-mb", "1024",
            "--output-root", str(self.root / "out_limits"),
            "--dry-run",
        ])
        self.assertEqual(rc, 0)
        manifest = json.loads((self.root / "out_limits" / "dry-limits" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["max_workers"], 2)
        self.assertEqual(manifest["child_max_rss_mb"], 1024)

        self.assertEqual(
            run_benchmark.main(["--experiment-id", "bad1", "--max-workers", "0", "--dry-run"]),
            2,
        )
        self.assertEqual(
            run_benchmark.main(["--experiment-id", "bad2", "--child-max-rss-mb", "-1", "--dry-run"]),
            2,
        )

    def test_frozen_v01_snapshot_uses_benchmarks_snapshots_path(self) -> None:
        self.assertEqual(
            run_benchmark.FROZEN_V01_SNAPSHOT_REL,
            "benchmarks/snapshots/core-rules-v0.1.0.txt",
        )
        snap = REPO_ROOT / run_benchmark.FROZEN_V01_SNAPSHOT_REL
        self.assertTrue(snap.is_file(), f"missing frozen snapshot: {snap}")
        self.assertIn("Version 0.1.0.", snap.read_text(encoding="utf-8"))

    def test_prepare_isolated_codex_home_copies_only_auth_json_with_0600_mode(self) -> None:
        src_codex = self.root / "src_codex"
        src_codex.mkdir()
        (src_codex / "auth.json").write_text('{"token":"dummy"}\n', encoding="utf-8")
        (src_codex / "config.toml").write_text("model = 'leak'\n", encoding="utf-8")
        (src_codex / "hooks.json").write_text("{}\n", encoding="utf-8")
        (src_codex / "AGENTS.md").write_text("personal instructions\n", encoding="utf-8")
        (src_codex / "skills" / "private-skill").mkdir(parents=True)
        (src_codex / "skills" / "private-skill" / "SKILL.md").write_text("secret skill\n", encoding="utf-8")
        (src_codex / "rules").mkdir()
        (src_codex / "rules" / "personal.rules").write_text("allow all\n", encoding="utf-8")

        iso_home, iso_codex = run_benchmark.prepare_isolated_codex_home(
            REPO_ROOT, "unit-codex-iso", source_codex_home=src_codex
        )
        self.addCleanup(lambda: shutil.rmtree(iso_home, ignore_errors=True))

        self.assertFalse(iso_home.resolve().is_relative_to(REPO_ROOT.resolve()))
        self.assertFalse(iso_codex.resolve().is_relative_to(REPO_ROOT.resolve()))
        self.assertEqual([p.name for p in iso_codex.iterdir()], ["auth.json"])
        self.assertFalse((iso_codex / "auth.json").is_symlink())
        self.assertEqual((iso_codex / "auth.json").read_text(encoding="utf-8"), '{"token":"dummy"}\n')
        if os.name == "posix":
            self.assertEqual(os.stat(iso_codex / "auth.json").st_mode & 0o777, 0o600)
        for forbidden in ("skills", "rules", "hooks.json", "config.toml", "AGENTS.md"):
            self.assertFalse((iso_codex / forbidden).exists(), f"{forbidden} must not be copied")

        # Also works cleanly when source auth.json is absent (e.g. API-key auth / CI).
        empty_src = self.root / "empty_codex"
        empty_src.mkdir()
        iso_home2, iso_codex2 = run_benchmark.prepare_isolated_codex_home(
            REPO_ROOT, "unit-codex-empty", source_codex_home=empty_src
        )
        self.addCleanup(lambda: shutil.rmtree(iso_home2, ignore_errors=True))
        self.assertEqual(list(iso_codex2.iterdir()), [])

    def test_sanitize_public_text_scrubs_paths_tmpdirs_and_local_usernames(self) -> None:
        fake_user = "benchuser"
        fake_home = Path(os.sep + "Users") / fake_user
        fake_repo = fake_home / "projects" / "anti-slop"
        fake_workdir = Path("/private/var/folders/ab/cdef0123456789/T/antislop_run_xyz")
        fake_codex = Path("/private/var/folders/ab/cdef0123456789/T/antislop_codexhome_xyz")
        raw = (
            f"CMD: {fake_repo}/scripts/run_benchmark.py -C {fake_workdir}\n"
            f"CODEX_HOME={fake_codex}/.codex\n"
            f"ALT_TMP=/var/folders/zz/9999abcdef/T/antislop_other_run/src/app.py\n"
            f"LINK: file://{fake_home}/.gemini/antigravity-cli/brain/1234/scratch/out.md\n"
            f"ENV: USER={fake_user} LOGNAME={fake_user}\n"
            f"-rw-r--r--@  1 {fake_user}  staff  1234 Nov 26 10:00 file.py\n"
            f"drwxr-xr-x   2 {fake_user}  {fake_user}  4096 Nov 26 10:00 dir\n"
            f'"aggregated_output":"total 8\\ndrwxr-x---+  5 {fake_user}  staff  160 .\\n"\n'
            'FIXTURE_LITERAL = Path("/Users/" + "dev/keys/staging.pem")\n'
        )
        cleaned = run_benchmark.sanitize_public_text(
            raw,
            fake_repo,
            fake_workdir,
            extra_paths=[fake_codex],
            home_dir=fake_home,
            username=fake_user,
        )
        self.assertIn("<REPO_ROOT>/scripts/run_benchmark.py -C <TMP_WORKSPACE>", cleaned)
        self.assertIn("CODEX_HOME=<TMP_WORKSPACE>/.codex", cleaned)
        self.assertIn("ALT_TMP=<TMP_WORKSPACE>/src/app.py", cleaned)
        self.assertIn("LINK: file://<HOME>/.gemini/antigravity-cli/brain/1234/scratch/out.md", cleaned)
        self.assertIn("ENV: USER=<user> LOGNAME=<user>", cleaned)
        self.assertIn("-rw-r--r--@  1 <user>  staff", cleaned)
        self.assertIn("drwxr-xr-x   2 <user>  <user>", cleaned)
        self.assertIn('drwxr-x---+  5 <user>  staff', cleaned)
        self.assertNotIn(fake_user, cleaned)
        self.assertNotIn("cdef0123456789", cleaned)
        self.assertNotIn("9999abcdef", cleaned)
        # Valid neighbouring fixture strings unrelated to local user stay intact.
        self.assertIn('dev/keys/staging.pem', cleaned)

    def test_execute_run_isolates_codex_home_across_stages_and_sanitizes_before_hashing(self) -> None:
        fake_repo = self.root / "fake_repo"
        src_dir = fake_repo / "benchmarks" / "sources" / "demo"
        src_dir.mkdir(parents=True)
        src_file = src_dir / "notes.txt"
        src_file.write_text("hello\n", encoding="utf-8")

        cond_file = fake_repo / "runs-local" / "exp1" / "conditions" / "baseline.txt"
        cond_file.parent.mkdir(parents=True)
        cond_file.write_text(run_benchmark.BASELINE_INSTRUCTION, encoding="utf-8")

        case = {
            "schema_version": 1,
            "case_id": "DEMO",
            "version": "1.0.0",
            "origin": "constructed",
            "domain": "writing",
            "title": "Demo 2-stage isolation and sanitization check",
            "prompt": "Stage 1 prompt.",
            "evidence_sources": [
                {
                    "id": "demo-notes",
                    "locator": "benchmarks/sources/demo/notes.txt",
                    "sha256": benchmark.sha256(src_file),
                }
            ],
            "acceptance_checks": [
                {"id": "ok", "description": "demo check", "required": True},
            ],
            "lineage_steps": ["Stage 1 prompt.", "Stage 2 prompt."],
        }
        fake_src_codex = self.root / "fake_user_codex"
        fake_src_codex.mkdir()
        (fake_src_codex / "auth.json").write_text('{"auth":"ok"}\n', encoding="utf-8")
        (fake_src_codex / "skills").mkdir()
        (fake_src_codex / "skills" / "private.md").write_text("do-not-leak\n", encoding="utf-8")

        seen_envs: list[dict[str, str]] = []
        seen_workdirs: list[Path] = []
        real_home = Path.home().resolve()
        real_user = os.environ.get("USER") or real_home.name

        def fake_subprocess(
            cmd: list[str],
            *,
            cwd: Path | str,
            env: dict[str, str] | None,
            **kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            self.assertIsNotNone(env)
            assert env is not None
            env_copy = dict(env)
            cwd_path = Path(cwd)
            seen_envs.append(env_copy)
            seen_workdirs.append(cwd_path)
            codex_dir = Path(env_copy["CODEX_HOME"])
            self.assertTrue((codex_dir / "auth.json").is_file())
            self.assertFalse((codex_dir / "skills").exists())
            self.assertFalse(codex_dir.resolve().is_relative_to(cwd_path.resolve()))
            self.assertFalse(codex_dir.resolve().is_relative_to(fake_repo.resolve()))
            out_idx = cmd.index("-o") + 1
            msg = (
                f"Checked {cwd_path}/benchmarks/sources/demo/notes.txt from {fake_repo} "
                f"and {real_home}/secret.txt\n"
                f"-rw-r--r-- 1 {real_user} staff 10 Nov 26 10:00 notes.txt"
            )
            Path(cmd[out_idx]).write_text(msg, encoding="utf-8")
            stdout = "\n".join([
                json.dumps({"type": "thread.started", "thread_id": "thr-iso-1"}),
                json.dumps({
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": msg},
                }),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}),
            ])
            stderr = f"debug cwd={cwd_path} home={real_home} codex={codex_dir}"
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr=stderr)

        orig_prepare = run_benchmark.prepare_isolated_codex_home

        def patched_prepare(repo_root: Path, run_id: str, source_codex_home: Path | None = None) -> tuple[Path, Path]:
            return orig_prepare(repo_root, run_id, source_codex_home=fake_src_codex)

        with (
            mock.patch("scripts.run_benchmark.prepare_isolated_codex_home", side_effect=patched_prepare),
            mock.patch("scripts.run_benchmark._run_stage_subprocess", side_effect=fake_subprocess),
        ):
            record = run_benchmark.execute_run(
                repo_root=fake_repo,
                exp_dir=fake_repo / "runs-local" / "exp1",
                experiment_id="exp1",
                case=case,
                model_cfg=run_benchmark.DEFAULT_MODELS["gpt-6.2-astra"],
                cli_version="codex-cli 0.171.0",
                condition="baseline",
                condition_file=cond_file,
                replicate=1,
                source_snapshot_id="git-deadbeef1234",
                timeout_seconds=30,
            )

        self.assertEqual(record["status"], "completed")
        self.assertEqual(len(seen_envs), 2)
        # Stage 1 and Stage 2 share the same isolated CODEX_HOME so `codex exec resume` works.
        self.assertEqual(seen_envs[0]["CODEX_HOME"], seen_envs[1]["CODEX_HOME"])
        self.assertEqual(seen_envs[0]["HOME"], seen_envs[1]["HOME"])
        # Both temp workdir and isolated CODEX_HOME are cleaned up after execute_run finishes.
        self.assertFalse(Path(seen_envs[0]["HOME"]).exists())
        self.assertFalse(seen_workdirs[0].exists())

        # Every hashed artifact is public-clean on disk AND passes benchmark.validate_run() without re-hashing.
        for rel in record["artifact_hashes"]:
            body = (fake_repo / rel).read_text(encoding="utf-8")
            self.assertNotIn(str(fake_repo.resolve()), body, msg=rel)
            self.assertNotIn(str(real_home), body, msg=rel)
            self.assertNotIn(str(seen_workdirs[0]), body, msg=rel)
            self.assertNotIn(seen_envs[0]["CODEX_HOME"], body, msg=rel)
            self.assertNotIn(f"1 {real_user} staff", body, msg=rel)
            self.assertIn("<TMP_WORKSPACE>", body, msg=rel)

        cases_map = {("DEMO", "1.0.0"): case}
        benchmark.validate_run(record, cases_map, fake_repo, "demo-run")

        # Also verify _write_workspace_diff sanitizes local paths before persisting.
        diff_wd = self.root / "diff_wd"
        (diff_wd / "benchmarks" / "sources" / "demo").mkdir(parents=True)
        (diff_wd / "benchmarks" / "sources" / "demo" / "notes.txt").write_text(
            f"hello\npath={diff_wd}/x home={real_home}/y repo={fake_repo}/z\n",
            encoding="utf-8",
        )
        diff_out = self.root / "stage-1-workspace.diff"
        run_benchmark._write_workspace_diff(
            fake_repo,
            case,
            diff_wd,
            {"modified": ["benchmarks/sources/demo/notes.txt"], "created": [], "deleted": []},
            diff_out,
        )
        diff_body = diff_out.read_text(encoding="utf-8")
        self.assertIn("path=<TMP_WORKSPACE>/x home=<HOME>/y repo=<REPO_ROOT>/z", diff_body)
        self.assertNotIn(str(real_home), diff_body)

    def test_ev1_auto_populate_and_gated_structural_condition_repair_loop(self) -> None:
        # 1. freeze_conditions supports pilot-evolution-v0.7.0's gated-structural arm.
        cond_dir = self.root / "conds"
        snaps = run_benchmark.freeze_conditions(
            REPO_ROOT, cond_dir, ["baseline", "core-rules-v0.2.0", "gated-structural"]
        )
        self.assertIn("gated-structural", snaps)
        self.assertIn("structural review gate", snaps["gated-structural"].read_text(encoding="utf-8"))

        # 2. _auto_populate_checks maps all 6 EV1 acceptance checks from Stage 4 grader report.
        cases = benchmark.load_cases(REPO_ROOT / "benchmarks" / "cases", REPO_ROOT)
        ev1_case = cases[("EV1", "0.7.0")]
        fake_ev1_report = {
            "case_id": "EV1",
            "passed": False,
            "checks": [
                {"id": spec["id"], "passed": spec["id"] != "no_duplicate_code_growth", "detail": "ok"}
                for spec in ev1_case["acceptance_checks"]
            ],
        }
        populated, defects = run_benchmark._auto_populate_checks(
            ev1_case, {4: (fake_ev1_report, "ev1-s4.json")}, {}
        )
        self.assertEqual(defects, [])
        by_id = {c["id"]: c for c in populated}
        self.assertEqual(by_id["functional_all_turns"]["status"], "pass")
        self.assertEqual(by_id["mutation_test_strength"]["status"], "pass")
        self.assertEqual(by_id["no_duplicate_code_growth"]["status"], "fail")
        self.assertEqual(by_id["no_duplicate_code_growth"]["evidence"], ["ev1-s4.json"])

        # 3. execute_run under gated-structural triggers plain-English gate review + single repair turn.
        fake_repo = self.root / "fake_gated_repo"
        src_dir = fake_repo / "benchmarks" / "sources" / "ev1_order_ledger"
        shutil.copytree(REPO_ROOT / "benchmarks" / "sources" / "ev1_order_ledger", src_dir)
        exp_dir = fake_repo / "runs-local" / "exp_gated"
        exp_dir.mkdir(parents=True)
        gated_cond = run_benchmark.freeze_conditions(
            REPO_ROOT, exp_dir / "conditions", ["gated-structural"]
        )["gated-structural"]

        # Mini 2-stage EV1-like case using real EV1 workspace grader key.
        mini_case = dict(ev1_case)
        mini_case["lineage_steps"] = [ev1_case["lineage_steps"][0], ev1_case["lineage_steps"][1]]
        prompts_seen: list[str] = []

        def fake_invoke(**kwargs):
            wd = kwargs["workdir"]
            prompts_seen.append(kwargs["prompt"])
            trace_path = kwargs["trace_log_path"]
            trace_path.write_text("trace\n", encoding="utf-8")
            target = wd / "benchmarks/sources/ev1_order_ledger/api.py"
            if len(prompts_seen) == 1:
                # Stage 1 initial output injects a silent fallback that gated-structural must catch!
                target.write_text(
                    target.read_text(encoding="utf-8")
                    + "\ndef helper():\n    try:\n        return 1\n    except Exception:\n        return 0\n",
                    encoding="utf-8",
                )
            elif len(prompts_seen) == 2:
                # Automated gate repair removes the silent fallback.
                target.write_text(
                    (REPO_ROOT / "benchmarks/sources/ev1_order_ledger/api.py").read_text(encoding="utf-8")
                    + "\ndef helper():\n    return 1\n",
                    encoding="utf-8",
                )
            return {
                "status": "completed",
                "text": "Done",
                "session_id": "sid-gated-1",
                "total_tokens": 100 * len(prompts_seen),
                "cost_usd": 0.01 * len(prompts_seen),
                "observed_model": "claude-opus-5-5",
                "downgraded_models": [],
                "elapsed_s": 0.1,
            }

        def fake_ws_grader(_repo_root, _case, _workdir, _stage, grader_out_path, **_kw):
            rep = {"case_id": "EV1", "passed": True, "checks": []}
            grader_out_path.write_text(json.dumps(rep) + "\n", encoding="utf-8")
            return rep

        with (
            mock.patch("scripts.run_benchmark._invoke_stage", side_effect=fake_invoke),
            mock.patch("scripts.run_benchmark._run_workspace_grader", side_effect=fake_ws_grader),
        ):
            rec = run_benchmark.execute_run(
                repo_root=fake_repo,
                exp_dir=exp_dir,
                experiment_id="exp_gated",
                case=mini_case,
                model_cfg=run_benchmark.DEFAULT_MODELS["claude-opus-5-5"],
                cli_version="claude 1.0",
                condition="gated-structural",
                condition_file=gated_cond,
                replicate=1,
                source_snapshot_id="git-deadbeef1234",
                timeout_seconds=30,
            )

        self.assertEqual(rec["status"], "completed")
        # Stage 1 -> gate flagged STRUCT-SILENT-FALLBACK -> repair turn (2nd call) -> Stage 2 clean (3rd call)!
        self.assertEqual(len(prompts_seen), 3)
        self.assertIn("STRUCT-SILENT-FALLBACK", prompts_seen[1])
        self.assertIn("runs-local/exp_gated/artifacts/" + rec["run_id"] + "/stage-1-gate-review.txt", rec["artifact_hashes"])
        self.assertIn("runs-local/exp_gated/artifacts/" + rec["run_id"] + "/stage-1-gate-repair-trace.log", rec["artifact_hashes"])

    def test_cm1_ablation_freeze_prepare_and_mechanical_grading(self) -> None:
        from tests.test_cm1 import CLEAN_WEBHOOKS_BODY

        conds = ["no-comments", "invariant-comments", "comment-traps"]

        # 1. Shared condition freezing produces one immutable snapshot per arm across all models.
        cond_dir = self.root / "cm1_conds"
        snaps = run_benchmark.freeze_conditions(
            REPO_ROOT,
            cond_dir,
            conds,
            models=["claude-opus-5-5", "gpt-6.2-astra"],
        )
        self.assertEqual(set(snaps.keys()), set(conds))
        sha_set = {benchmark.sha256(snaps[c]) for c in conds}
        self.assertEqual(len(sha_set), 3)
        for cond in conds:
            self.assertFalse(benchmark.is_per_model_condition(cond))
            self.assertEqual(
                run_benchmark.resolve_condition_file(snaps, cond, "claude-opus-5-5"),
                run_benchmark.resolve_condition_file(snaps, cond, "gpt-6.2-astra"),
            )
            snap_text = snaps[cond].read_text(encoding="utf-8")
            self.assertIn(run_benchmark.BASELINE_INSTRUCTION.strip(), snap_text)
            self.assertIn(run_benchmark.CM1_CONDITION_VARIANTS[cond], snap_text)

        # Dry-run CLI succeeds for CM1 and rejects pairing CM1 arms with non-CM1 cases.
        rc_cm1 = run_benchmark.main([
            "--experiment-id", "dry-cm1",
            "--cases", "CM1",
            "--models", "claude-opus-5-5",
            "--conditions", *conds,
            "--output-root", str(self.root / "out_cm1"),
            "--dry-run",
        ])
        self.assertEqual(rc_cm1, 0)
        rc_bad = run_benchmark.main([
            "--experiment-id", "dry-bad-cm1",
            "--cases", "EV1",
            "--models", "claude-opus-5-5",
            "--conditions", *conds,
            "--output-root", str(self.root / "out_cm1"),
            "--dry-run",
        ])
        self.assertEqual(rc_bad, 2)

        # 2. prepare_clean_workspace isolates ONLY the requested variant at workspace root (blinded paths).
        cases = benchmark.load_cases(REPO_ROOT / "benchmarks" / "cases", REPO_ROOT)
        cm1_case = cases[("CM1", "0.7.0")]
        for cond, variant in run_benchmark.CM1_CONDITION_VARIANTS.items():
            workdir, hashes = run_benchmark.prepare_clean_workspace(
                REPO_ROOT,
                cm1_case,
                run_benchmark.BASELINE_INSTRUCTION,
                write_agents_md=True,
                run_id=f"cm1_prep_{cond}",
                condition=cond,
            )
            self.addCleanup(lambda p=workdir: shutil.rmtree(p, ignore_errors=True))
            self.assertEqual(
                set(hashes.keys()),
                {
                    "__init__.py",
                    "models.py",
                    "webhooks.py",
                    "run_checks.py",
                    "tests/__init__.py",
                    "tests/test_webhooks.py",
                    "AGENTS.md",
                },
            )
            # Zero sibling variant dirs or condition-name path leaks inside workdir.
            self.assertFalse((workdir / "benchmarks").exists())
            for vname in run_benchmark.CM1_CONDITION_VARIANTS.values():
                self.assertFalse((workdir / vname).exists())
            expected_sha = benchmark.sha256(
                REPO_ROOT / "benchmarks" / "sources" / "cm1_comment_ablation" / variant / "webhooks.py"
            )
            self.assertEqual(hashes["webhooks.py"], expected_sha)
            self.assertEqual((workdir / "AGENTS.md").read_text(encoding="utf-8"), run_benchmark.BASELINE_INSTRUCTION)

        # 3. _auto_populate_checks marks all 4 CM1 checks fail on grader load/syntax error.
        load_fail_checks, load_defects = run_benchmark._auto_populate_checks(
            cm1_case,
            {1: ({"case_id": "CM1", "passed": False, "checks": [{"id": "load", "passed": False, "detail": "SyntaxError"}]}, "g1.json")},
            {},
        )
        self.assertEqual(load_defects, [])
        self.assertEqual(len(load_fail_checks), 4)
        self.assertTrue(all(c["status"] == "fail" and c["evidence"] == ["g1.json"] for c in load_fail_checks))

        # 4. End-to-end execute_run runs REAL grade_cm1.py, delivers identical neutral prompt, and validates cleanly.
        fake_repo = self.root / "fake_cm1_repo"
        shutil.copytree(
            REPO_ROOT / "benchmarks" / "sources" / "cm1_comment_ablation",
            fake_repo / "benchmarks" / "sources" / "cm1_comment_ablation",
        )
        exp_dir = fake_repo / "runs-local" / "exp_cm1"
        exp_snaps = run_benchmark.freeze_conditions(fake_repo, exp_dir / "conditions", conds)
        delivered_instructions: list[str] = []
        delivered_prompts: list[str] = []

        def fake_invoke_clean(**kwargs):
            delivered_instructions.append(kwargs["condition_text"])
            delivered_prompts.append(kwargs["prompt"])
            kwargs["trace_log_path"].write_text("trace\n", encoding="utf-8")
            (kwargs["workdir"] / "webhooks.py").write_text(CLEAN_WEBHOOKS_BODY, encoding="utf-8")
            return {
                "status": "completed",
                "text": "Updated webhooks.py and confirmed python3 run_checks.py exits 0.",
                "session_id": "sid-cm1-clean",
                "total_tokens": 120,
                "cost_usd": 0.01,
                "observed_model": "claude-opus-5-5",
                "downgraded_models": [],
                "elapsed_s": 0.1,
            }

        def fake_invoke_trap(**kwargs):
            delivered_instructions.append(kwargs["condition_text"])
            delivered_prompts.append(kwargs["prompt"])
            kwargs["trace_log_path"].write_text("trace\n", encoding="utf-8")
            trapped = CLEAN_WEBHOOKS_BODY.replace(
                "return (amount_cents * fee_bps + 5000) // 10000",
                "return int(amount_cents * (fee_bps / 10000.0))",
            ) + "\n# def leftover(x):\n#     y = x + 1\n#     return y\n"
            (kwargs["workdir"] / "webhooks.py").write_text(trapped, encoding="utf-8")
            return {
                "status": "completed",
                "text": "Updated webhooks.py.",
                "session_id": "sid-cm1-trap",
                "total_tokens": 130,
                "cost_usd": 0.01,
                "observed_model": "claude-opus-5-5",
                "downgraded_models": [],
                "elapsed_s": 0.1,
            }

        with mock.patch("scripts.run_benchmark._invoke_stage", side_effect=fake_invoke_clean):
            rec_clean = run_benchmark.execute_run(
                repo_root=fake_repo,
                exp_dir=exp_dir,
                experiment_id="exp_cm1",
                case=cm1_case,
                model_cfg=run_benchmark.DEFAULT_MODELS["claude-opus-5-5"],
                cli_version="claude 1.0",
                condition="no-comments",
                condition_file=exp_snaps["no-comments"],
                replicate=1,
                source_snapshot_id="git-deadbeef1234",
                timeout_seconds=30,
            )

        with mock.patch("scripts.run_benchmark._invoke_stage", side_effect=fake_invoke_trap):
            rec_trap = run_benchmark.execute_run(
                repo_root=fake_repo,
                exp_dir=exp_dir,
                experiment_id="exp_cm1",
                case=cm1_case,
                model_cfg=run_benchmark.DEFAULT_MODELS["claude-opus-5-5"],
                cli_version="claude 1.0",
                condition="comment-traps",
                condition_file=exp_snaps["comment-traps"],
                replicate=1,
                source_snapshot_id="git-deadbeef1234",
                timeout_seconds=30,
            )

        # Identical neutral instruction & neutral prompt delivered across both arms!
        self.assertEqual(delivered_instructions, [run_benchmark.BASELINE_INSTRUCTION, run_benchmark.BASELINE_INSTRUCTION])
        self.assertEqual(delivered_prompts[0], delivered_prompts[1])
        self.assertNotIn("comment_traps", delivered_prompts[0])

        clean_map = {c["id"]: c["status"] for c in rec_clean["checks"]}
        self.assertEqual(
            clean_map,
            {
                "feature_and_idempotency_verified": "pass",
                "out_of_order_invariant_preserved": "pass",
                "integer_cent_precision_preserved": "pass",
                "commented_code_cleaned_and_readonly_intact": "pass",
            },
        )
        trap_map = {c["id"]: c["status"] for c in rec_trap["checks"]}
        self.assertEqual(trap_map["feature_and_idempotency_verified"], "pass")
        self.assertEqual(trap_map["out_of_order_invariant_preserved"], "pass")
        self.assertEqual(trap_map["integer_cent_precision_preserved"], "fail")
        self.assertEqual(trap_map["commented_code_cleaned_and_readonly_intact"], "fail")

        # Unified workspace diff was computed against the original variant file (not /dev/null).
        clean_diff_rel = f"runs-local/exp_cm1/artifacts/{rec_clean['run_id']}/stage-1-workspace.diff"
        self.assertIn(clean_diff_rel, rec_clean["artifact_hashes"])
        self.assertIn("--- a/webhooks.py", (fake_repo / clean_diff_rel).read_text(encoding="utf-8"))

        # Both records pass benchmark.validate_run and benchmark.comparable_pairs cleanly!
        cases_map = {("CM1", "0.7.0"): cm1_case}
        benchmark.validate_run(rec_clean, cases_map, fake_repo, "cm1-clean")
        benchmark.validate_run(rec_trap, cases_map, fake_repo, "cm1-trap")
        pairs = benchmark.comparable_pairs([rec_clean, rec_trap], "no-comments", "comment-traps")
        self.assertEqual(len(pairs), 1)

    def test_ev2_dry_run_auto_populate_and_gated_structural_ts_repair_loop(self) -> None:
        # 1. Dry-run CLI succeeds for EV2 across baseline, core-rules-v0.2.0, and gated-structural.
        rc_ev2 = run_benchmark.main([
            "--experiment-id", "dry-ev2",
            "--cases", "EV2",
            "--models", "claude-opus-5-5",
            "--conditions", "baseline", "core-rules-v0.2.0", "gated-structural",
            "--output-root", str(self.root / "out_ev2"),
            "--dry-run",
        ])
        self.assertEqual(rc_ev2, 0)
        manifest = json.loads((self.root / "out_ev2" / "dry-ev2" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["cases"], ["EV2"])
        self.assertEqual(set(manifest["conditions"].keys()), {"baseline", "core-rules-v0.2.0", "gated-structural"})

        # 2. _auto_populate_checks maps all 6 EV2 acceptance checks from Stage 4 grader report.
        cases = benchmark.load_cases(REPO_ROOT / "benchmarks" / "cases", REPO_ROOT)
        ev2_case = cases[("EV2", "0.8.0")]
        fake_ev2_report = {
            "case_id": "EV2",
            "passed": False,
            "checks": [
                {"id": spec["id"], "passed": spec["id"] != "no_sprawl_or_god_functions", "detail": "ok"}
                for spec in ev2_case["acceptance_checks"]
            ],
        }
        populated, defects = run_benchmark._auto_populate_checks(
            ev2_case, {4: (fake_ev2_report, "ev2-s4.json")}, {}
        )
        self.assertEqual(defects, [])
        by_id = {c["id"]: c for c in populated}
        self.assertEqual(len(by_id), 6)
        self.assertEqual(by_id["functional_all_turns"]["status"], "pass")
        self.assertEqual(by_id["mutation_test_strength"]["status"], "pass")
        self.assertEqual(by_id["no_sprawl_or_god_functions"]["status"], "fail")
        self.assertEqual(by_id["no_sprawl_or_god_functions"]["evidence"], ["ev2-s4.json"])

        # 3. execute_run under gated-structural runs gates.review.review_diff across all 4 TS stages
        #    and triggers repair turns for both STRUCT-* and ARCH-* TypeScript findings.
        fake_repo = self.root / "fake_ev2_repo"
        src_dir = fake_repo / "benchmarks" / "sources" / "ev2_ts_bookings"
        shutil.copytree(REPO_ROOT / "benchmarks" / "sources" / "ev2_ts_bookings", src_dir)
        exp_dir = fake_repo / "runs-local" / "exp_ev2_gated"
        exp_dir.mkdir(parents=True)
        gated_cond = run_benchmark.freeze_conditions(
            REPO_ROOT, exp_dir / "conditions", ["gated-structural"], cases=["EV2"]
        )["gated-structural"]

        orig_pricing = (REPO_ROOT / "benchmarks/sources/ev2_ts_bookings/src/pricing.ts").read_text(encoding="utf-8")
        orig_bookings = (REPO_ROOT / "benchmarks/sources/ev2_ts_bookings/src/bookings.ts").read_text(encoding="utf-8")
        prompts_seen: list[str] = []

        def fake_invoke(**kwargs):
            wd = kwargs["workdir"]
            prompts_seen.append(kwargs["prompt"])
            kwargs["trace_log_path"].write_text("trace\n", encoding="utf-8")
            pricing_ts = wd / "benchmarks/sources/ev2_ts_bookings/src/pricing.ts"
            bookings_ts = wd / "benchmarks/sources/ev2_ts_bookings/src/bookings.ts"
            corporate_ts = wd / "benchmarks/sources/ev2_ts_bookings/src/corporate.ts"
            call_no = len(prompts_seen)
            if call_no == 1:
                # Stage 1: inject silent TS catch fallback -> STRUCT-SILENT-FALLBACK.
                pricing_ts.write_text(
                    orig_pricing + "\nexport function safeRate(x: number): number {\n  try { return x; } catch { return 0; }\n}\n",
                    encoding="utf-8",
                )
            elif call_no == 2:
                # Stage 1 repair: remove silent catch fallback.
                pricing_ts.write_text(
                    orig_pricing + "\nexport function safeRate(x: number): number {\n  return x;\n}\n",
                    encoding="utf-8",
                )
            elif call_no == 3:
                # Stage 2: inject circular TS import between bookings.ts and corporate.ts -> ARCH-CIRCULAR-IMPORT.
                corporate_ts.write_text(
                    'import { BookingService } from "./bookings.ts";\n'
                    "export function groupHelper(svc: BookingService): boolean { return Boolean(svc); }\n",
                    encoding="utf-8",
                )
                bookings_ts.write_text(
                    'import { groupHelper } from "./corporate.ts";\n'
                    + orig_bookings
                    + "\nexport function pingGroup(svc: BookingService): boolean { return groupHelper(svc); }\n",
                    encoding="utf-8",
                )
            elif call_no == 4:
                # Stage 2 repair: break circular import cleanly.
                bookings_ts.write_text(orig_bookings, encoding="utf-8")
                corporate_ts.write_text(
                    'import { BookingService } from "./bookings.ts";\n'
                    "export function groupHelper(svc: BookingService): boolean { return Boolean(svc); }\n",
                    encoding="utf-8",
                )
            # Calls 5 and 6 (Stages 3 and 4) keep the workspace clean with no new defects.
            return {
                "status": "completed",
                "text": f"Stage call {call_no} done.",
                "session_id": "sid-ev2-gated",
                "total_tokens": 100 * call_no,
                "cost_usd": 0.01 * call_no,
                "observed_model": "claude-opus-5-5",
                "downgraded_models": [],
                "elapsed_s": 0.1,
            }

        def fake_ws_grader(_repo_root, _case, _workdir, _stage, grader_out_path, **_kw):
            rep = {
                "case_id": "EV2",
                "passed": True,
                "checks": [
                    {"id": spec["id"], "passed": True, "detail": "ok"}
                    for spec in ev2_case["acceptance_checks"]
                ],
            }
            grader_out_path.write_text(json.dumps(rep) + "\n", encoding="utf-8")
            return rep

        with (
            mock.patch("scripts.run_benchmark._invoke_stage", side_effect=fake_invoke),
            mock.patch("scripts.run_benchmark._run_workspace_grader", side_effect=fake_ws_grader),
        ):
            rec = run_benchmark.execute_run(
                repo_root=fake_repo,
                exp_dir=exp_dir,
                experiment_id="exp_ev2_gated",
                case=ev2_case,
                model_cfg=run_benchmark.DEFAULT_MODELS["claude-opus-5-5"],
                cli_version="claude 1.0",
                condition="gated-structural",
                condition_file=gated_cond,
                replicate=1,
                source_snapshot_id="git-deadbeef1234",
                timeout_seconds=30,
            )

        self.assertEqual(rec["status"], "completed")
        # 4 base stages + 2 repair turns (Stage 1 STRUCT-SILENT-FALLBACK, Stage 2 ARCH-CIRCULAR-IMPORT).
        self.assertEqual(len(prompts_seen), 6)
        self.assertIn("STRUCT-SILENT-FALLBACK", prompts_seen[1])
        self.assertIn("ARCH-CIRCULAR-IMPORT", prompts_seen[3])
        art_prefix = f"runs-local/exp_ev2_gated/artifacts/{rec['run_id']}/"
        for expected_art in (
            "stage-1-gate-review.txt",
            "stage-1-gate-repair-trace.log",
            "stage-2-gate-review.txt",
            "stage-2-gate-repair-trace.log",
            "stage-3-gate-review.txt",
            "stage-4-gate-review.txt",
        ):
            self.assertIn(art_prefix + expected_art, rec["artifact_hashes"])
        self.assertEqual({c["id"]: c["status"] for c in rec["checks"]}, {spec["id"]: "pass" for spec in ev2_case["acceptance_checks"]})
        benchmark.validate_run(rec, {("EV2", "0.8.0"): ev2_case}, fake_repo, "ev2-gated")

    def test_cm2_ablation_freeze_prepare_dry_run_and_mechanical_grading(self) -> None:
        from benchmarks.graders import grade_cm2
        from tests.test_cm2 import CLEAN_REPLAY_METHOD, _apply_clean_solution

        conds = ["no-comments", "invariant-comments", "comment-traps"]

        # 1. Shared condition freezing for CM2 pins all 6 module SHA-256s per arm across all models.
        cond_dir = self.root / "cm2_conds"
        snaps = run_benchmark.freeze_conditions(
            REPO_ROOT,
            cond_dir,
            conds,
            models=["claude-opus-5-5", "gpt-6.2-astra"],
            cases=["CM2"],
        )
        self.assertEqual(set(snaps.keys()), set(conds))
        self.assertEqual(len({benchmark.sha256(snaps[c]) for c in conds}), 3)
        for cond in conds:
            variant = run_benchmark.CM1_CONDITION_VARIANTS[cond]
            self.assertFalse(benchmark.is_per_model_condition(cond))
            self.assertEqual(
                run_benchmark.resolve_condition_file(snaps, cond, "claude-opus-5-5"),
                run_benchmark.resolve_condition_file(snaps, cond, "gpt-6.2-astra"),
            )
            snap_text = snaps[cond].read_text(encoding="utf-8")
            self.assertIn("CM2 multi-file comment-hygiene ablation arm:", snap_text)
            self.assertIn(run_benchmark.BASELINE_INSTRUCTION.strip(), snap_text)
            for mod in grade_cm2.PROD_MODULES:
                expected_sha = benchmark.sha256(
                    REPO_ROOT / "benchmarks" / "sources" / "cm2_multifile_comments" / variant / mod
                )
                self.assertIn(f"{mod}: {expected_sha}", snap_text)

        # Dry-run CLI succeeds for CM2 and rejects pairing comment-ablation arms with EV2.
        rc_cm2 = run_benchmark.main([
            "--experiment-id", "dry-cm2",
            "--cases", "CM2",
            "--models", "claude-opus-5-5",
            "--conditions", *conds,
            "--output-root", str(self.root / "out_cm2"),
            "--dry-run",
        ])
        self.assertEqual(rc_cm2, 0)
        rc_bad = run_benchmark.main([
            "--experiment-id", "dry-bad-cm2",
            "--cases", "EV2",
            "--models", "claude-opus-5-5",
            "--conditions", *conds,
            "--output-root", str(self.root / "out_cm2"),
            "--dry-run",
        ])
        self.assertEqual(rc_bad, 2)

        # 2. prepare_clean_workspace isolates ONLY the requested CM2 variant at workspace root.
        cases = benchmark.load_cases(REPO_ROOT / "benchmarks" / "cases", REPO_ROOT)
        cm2_case = cases[("CM2", "0.8.0")]
        for cond, variant in run_benchmark.CM1_CONDITION_VARIANTS.items():
            workdir, hashes = run_benchmark.prepare_clean_workspace(
                REPO_ROOT,
                cm2_case,
                run_benchmark.BASELINE_INSTRUCTION,
                write_agents_md=True,
                run_id=f"cm2_prep_{cond}",
                condition=cond,
            )
            self.addCleanup(lambda p=workdir: shutil.rmtree(p, ignore_errors=True))
            self.assertEqual(set(hashes.keys()), set(grade_cm2.EXPECTED_FILES) | {"AGENTS.md"})
            self.assertFalse((workdir / "benchmarks").exists())
            for vname in run_benchmark.CM1_CONDITION_VARIANTS.values():
                self.assertFalse((workdir / vname).exists())
            for mod in grade_cm2.PROD_MODULES:
                expected_sha = benchmark.sha256(
                    REPO_ROOT / "benchmarks" / "sources" / "cm2_multifile_comments" / variant / mod
                )
                self.assertEqual(hashes[mod], expected_sha)
            self.assertEqual((workdir / "AGENTS.md").read_text(encoding="utf-8"), run_benchmark.BASELINE_INSTRUCTION)

        # 3. _auto_populate_checks marks all 4 CM2 checks fail on grader load error.
        load_fail_checks, load_defects = run_benchmark._auto_populate_checks(
            cm2_case,
            {1: ({"case_id": "CM2", "passed": False, "checks": [{"id": "load", "passed": False, "detail": "SyntaxError"}]}, "g1.json")},
            {},
        )
        self.assertEqual(load_defects, [])
        self.assertEqual(len(load_fail_checks), 4)
        self.assertTrue(all(c["status"] == "fail" and c["evidence"] == ["g1.json"] for c in load_fail_checks))

        # 4. End-to-end execute_run runs REAL grade_cm2.py, delivers neutral BASELINE_INSTRUCTION, and validates cleanly.
        fake_repo = self.root / "fake_cm2_repo"
        shutil.copytree(
            REPO_ROOT / "benchmarks" / "sources" / "cm2_multifile_comments",
            fake_repo / "benchmarks" / "sources" / "cm2_multifile_comments",
        )
        exp_dir = fake_repo / "runs-local" / "exp_cm2"
        exp_snaps = run_benchmark.freeze_conditions(
            fake_repo, exp_dir / "conditions", conds, cases=["CM2"]
        )
        delivered_instructions: list[str] = []
        delivered_prompts: list[str] = []

        def fake_invoke_clean(**kwargs):
            delivered_instructions.append(kwargs["condition_text"])
            delivered_prompts.append(kwargs["prompt"])
            kwargs["trace_log_path"].write_text("trace\n", encoding="utf-8")
            _apply_clean_solution(kwargs["workdir"])
            return {
                "status": "completed",
                "text": "Refactored modules, implemented replay_dead_letter_batch, and confirmed run_checks.py exits 0.",
                "session_id": "sid-cm2-clean",
                "total_tokens": 150,
                "cost_usd": 0.01,
                "observed_model": "claude-opus-5-5",
                "downgraded_models": [],
                "elapsed_s": 0.1,
            }

        def fake_invoke_trap(**kwargs):
            delivered_instructions.append(kwargs["condition_text"])
            delivered_prompts.append(kwargs["prompt"])
            kwargs["trace_log_path"].write_text("trace\n", encoding="utf-8")
            wd = kwargs["workdir"]
            api_text = (wd / "api.py").read_text(encoding="utf-8")
            target = (
                "    def replay_dead_letter_batch(self, batch_id: str) -> list[Job]:\n"
                "        # Replay handler placeholder error until implemented\n"
                '        raise JobError(f"replay_dead_letter_batch not yet implemented for {batch_id}")\n'
            )
            (wd / "api.py").write_text(api_text.replace(target, CLEAN_REPLAY_METHOD), encoding="utf-8")
            return {
                "status": "completed",
                "text": "Implemented replay_dead_letter_batch.",
                "session_id": "sid-cm2-trap",
                "total_tokens": 160,
                "cost_usd": 0.01,
                "observed_model": "claude-opus-5-5",
                "downgraded_models": [],
                "elapsed_s": 0.1,
            }

        with mock.patch("scripts.run_benchmark._invoke_stage", side_effect=fake_invoke_clean):
            rec_clean = run_benchmark.execute_run(
                repo_root=fake_repo,
                exp_dir=exp_dir,
                experiment_id="exp_cm2",
                case=cm2_case,
                model_cfg=run_benchmark.DEFAULT_MODELS["claude-opus-5-5"],
                cli_version="claude 1.0",
                condition="invariant-comments",
                condition_file=exp_snaps["invariant-comments"],
                replicate=1,
                source_snapshot_id="git-deadbeef1234",
                timeout_seconds=30,
            )

        with mock.patch("scripts.run_benchmark._invoke_stage", side_effect=fake_invoke_trap):
            rec_trap = run_benchmark.execute_run(
                repo_root=fake_repo,
                exp_dir=exp_dir,
                experiment_id="exp_cm2",
                case=cm2_case,
                model_cfg=run_benchmark.DEFAULT_MODELS["claude-opus-5-5"],
                cli_version="claude 1.0",
                condition="comment-traps",
                condition_file=exp_snaps["comment-traps"],
                replicate=1,
                source_snapshot_id="git-deadbeef1234",
                timeout_seconds=30,
            )

        self.assertEqual(delivered_instructions, [run_benchmark.BASELINE_INSTRUCTION, run_benchmark.BASELINE_INSTRUCTION])
        self.assertEqual(delivered_prompts[0], delivered_prompts[1])
        self.assertNotIn("comment_traps", delivered_prompts[0])

        clean_map = {c["id"]: c["status"] for c in rec_clean["checks"]}
        self.assertEqual(
            clean_map,
            {
                "dead_letter_replay_feature": "pass",
                "cross_file_epoch_dedupe_invariant": "pass",
                "persist_before_ack_crash_invariant": "pass",
                "tests_and_comment_cleanup": "pass",
            },
        )
        trap_map = {c["id"]: c["status"] for c in rec_trap["checks"]}
        self.assertEqual(trap_map["dead_letter_replay_feature"], "pass")
        self.assertEqual(trap_map["tests_and_comment_cleanup"], "fail")

        # Unified workspace diff was computed against the original variant file (not /dev/null).
        clean_diff_rel = f"runs-local/exp_cm2/artifacts/{rec_clean['run_id']}/stage-1-workspace.diff"
        self.assertIn(clean_diff_rel, rec_clean["artifact_hashes"])
        self.assertIn("--- a/api.py", (fake_repo / clean_diff_rel).read_text(encoding="utf-8"))

        cases_map = {("CM2", "0.8.0"): cm2_case}
        benchmark.validate_run(rec_clean, cases_map, fake_repo, "cm2-clean")
        benchmark.validate_run(rec_trap, cases_map, fake_repo, "cm2-trap")
        pairs = benchmark.comparable_pairs([rec_clean, rec_trap], "invariant-comments", "comment-traps")
        self.assertEqual(len(pairs), 1)

    def test_se3_runner_wiring_autopopulates_checks_and_pins_d_opu_5(self) -> None:
        cases = benchmark.load_cases(REPO_ROOT / "benchmarks" / "cases", REPO_ROOT)
        se3_case = cases[("SE3", "0.8.0")]

        # Dry-run verifies D-OPU-5 is scoped strictly to claude-opus-5-5 in model-controls.
        out_root = self.root / "out_se3"
        rc = run_benchmark.main([
            "--experiment-id", "dry-se3",
            "--cases", "SE3",
            "--models", "claude-opus-5-5", "gpt-6.2-astra",
            "--conditions", "baseline", "core-rules-v0.2.0", "model-controls",
            "--output-root", str(out_root),
            "--dry-run",
        ])
        self.assertEqual(rc, 0)
        opus_cond = (out_root / "dry-se3" / "conditions" / "model-controls__claude-opus-5-5.txt").read_text(encoding="utf-8")
        astra_cond = (out_root / "dry-se3" / "conditions" / "model-controls__gpt-6.2-astra.txt").read_text(encoding="utf-8")
        self.assertIn("D-OPU-5:", opus_cond)
        self.assertNotIn("D-OPU-5:", astra_cond)

        # Auto-population covers all three mechanical checks for pass, fail, and load error.
        rep1_ok = {
            "passed": True,
            "checks": [
                {"id": "no_unrequested_constraints_or_cheats", "passed": True, "detail": "ok"},
                {"id": "spec_fidelity_verified", "passed": True, "detail": "ok"},
            ],
        }
        rep2_ok = {
            "passed": True,
            "checks": [
                {"id": "no_unrequested_constraints_or_cheats", "passed": True, "detail": "ok"},
                {"id": "spec_fidelity_verified", "passed": True, "detail": "ok"},
                {"id": "summary_credibility_and_brevity", "passed": True, "detail": "ok"},
            ],
        }
        checks_ok, defects_ok = run_benchmark._auto_populate_checks(
            se3_case, {1: (rep1_ok, "g1.json"), 2: (rep2_ok, "g2.json")}, {}
        )
        self.assertEqual(defects_ok, [])
        self.assertEqual(
            {c["id"]: c["status"] for c in checks_ok},
            {
                "spec_fidelity_verified": "pass",
                "no_unrequested_constraints_or_cheats": "pass",
                "summary_credibility_and_brevity": "pass",
            },
        )

        rep2_fail = {
            "passed": False,
            "checks": [
                {"id": "no_unrequested_constraints_or_cheats", "passed": False, "detail": "PROTECTED_FIELDS"},
                {"id": "spec_fidelity_verified", "passed": False, "detail": "dropped skin_tone"},
                {"id": "summary_credibility_and_brevity", "passed": False, "detail": "135 > 120"},
            ],
        }
        checks_fail, _ = run_benchmark._auto_populate_checks(
            se3_case, {1: (rep1_ok, "g1.json"), 2: (rep2_fail, "g2.json")}, {}
        )
        self.assertEqual(
            {c["id"]: c["status"] for c in checks_fail},
            {
                "spec_fidelity_verified": "fail",
                "no_unrequested_constraints_or_cheats": "fail",
                "summary_credibility_and_brevity": "fail",
            },
        )


if __name__ == "__main__":
    unittest.main()
