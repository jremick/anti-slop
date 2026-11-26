"""Focused stdlib-only tests for gates/hooks/, context-hygiene api_checks.py
warnings, and R7 model_deltas.json scoping refinements.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_SCRIPT = REPO_ROOT / "gates/hooks/run_diff_gate_hook.py"


def _load_module(name: str, rel_path: str):
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


api_checks = _load_module("api_checks_hooks_test", "gates/api_checks.py")
diff_check = _load_module("diff_check_hooks_test", "gates/diff_check.py")


def _codes(items) -> set:
    return {item["code"] for item in items}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


class RunDiffGateHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / "src").mkdir()
        (self.repo / "tests").mkdir()
        (self.repo / "src" / "app.py").write_text(
            "def add(a: int, b: int) -> int:\n    return a + b\n",
            encoding="utf-8",
        )
        (self.repo / "tests" / "test_app.py").write_text(
            "def test_add():\n    assert 1 + 1 == 2\n",
            encoding="utf-8",
        )
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "test@example.com")
        _git(self.repo, "config", "user.name", "Test User")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "initial")

    def _run_hook(
        self,
        *args: str,
        stdin_text: str = "",
        env_extra: dict | None = None,
        include_repo_root: bool = True,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env.pop("ANTI_SLOP_ALLOW_TEST_EDIT", None)
        env.pop("ANTI_SLOP_BENCHMARK_SUBJECT", None)
        if env_extra:
            env.update(env_extra)
        cmd = [sys.executable, "-B", str(HOOK_SCRIPT)]
        if include_repo_root:
            cmd.extend(["--repo-root", str(self.repo)])
        cmd.extend(args)
        return subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            check=False,
        )

    def test_pretooluse_blocks_test_edit_with_exit_2_and_allows_valid_neighbours(self) -> None:
        # Claude Code PreToolUse Edit targeting tests/ -> exit 2
        claude_payload = json.dumps({
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "tests/test_app.py"},
        })
        proc = self._run_hook("--stdin-tool-json", stdin_text=claude_payload)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("DIFF-UNAUTHORIZED-TEST-EDIT", proc.stderr)
        self.assertIn("tests/test_app.py", proc.stderr)

        # Antigravity PreToolUse with absolute path inside repo -> exit 2
        agy_payload = json.dumps({
            "tool_name": "edit_file",
            "arguments": {"Path": str(self.repo / "tests" / "test_app.py")},
        })
        proc_agy = self._run_hook("--stdin-tool-json", stdin_text=agy_payload)
        self.assertEqual(proc_agy.returncode, 2)
        self.assertIn("DIFF-UNAUTHORIZED-TEST-EDIT", proc_agy.stderr)

        # Valid neighbouring case 1: editing production file exits 0
        prod_payload = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/app.py"},
        })
        proc_prod = self._run_hook("--stdin-tool-json", stdin_text=prod_payload)
        self.assertEqual(proc_prod.returncode, 0, msg=proc_prod.stderr)
        self.assertEqual(proc_prod.stderr, "")

        # Valid neighbouring case 2: read-only tool inspecting tests/ exits 0
        read_payload = json.dumps({
            "tool_name": "Read",
            "tool_input": {"file_path": "tests/test_app.py"},
        })
        proc_read = self._run_hook("--stdin-tool-json", stdin_text=read_payload)
        self.assertEqual(proc_read.returncode, 0, msg=proc_read.stderr)

        # Valid neighbouring case 3: explicit --allow-test-edit or env override exits 0
        proc_flag = self._run_hook("--stdin-tool-json", "--allow-test-edit", stdin_text=claude_payload)
        self.assertEqual(proc_flag.returncode, 0, msg=proc_flag.stderr)

        proc_env = self._run_hook(
            "--stdin-tool-json",
            stdin_text=claude_payload,
            env_extra={"ANTI_SLOP_ALLOW_TEST_EDIT": "1"},
        )
        self.assertEqual(proc_env.returncode, 0, msg=proc_env.stderr)

    def test_pretooluse_blocks_codex_apply_patch_raw_string_payload(self) -> None:
        # Codex apply_patch sending raw patch text as plain string under input / tool_input -> exit 2
        for key in ("input", "tool_input"):
            with self.subTest(key=key):
                raw_patch_payload = json.dumps({
                    "tool_name": "apply_patch",
                    key: (
                        "*** Begin Patch\n"
                        "*** Update File: tests/test_app.py\n"
                        "@@\n"
                        "-    assert 1 + 1 == 2\n"
                        "+    assert True\n"
                        "*** End Patch\n"
                    ),
                })
                proc = self._run_hook("--stdin-tool-json", stdin_text=raw_patch_payload)
                self.assertEqual(proc.returncode, 2)
                self.assertIn("DIFF-UNAUTHORIZED-TEST-EDIT", proc.stderr)
                self.assertIn("tests/test_app.py", proc.stderr)

        # Valid neighbouring case: raw-string apply_patch touching only production code exits 0
        prod_patch_payload = json.dumps({
            "tool_name": "apply_patch",
            "input": (
                "*** Begin Patch\n"
                "*** Update File: src/app.py\n"
                "@@\n"
                "-    return a + b\n"
                "+    return int(a) + int(b)\n"
                "*** End Patch\n"
            ),
        })
        proc_ok = self._run_hook("--stdin-tool-json", stdin_text=prod_patch_payload)
        self.assertEqual(proc_ok.returncode, 0, msg=proc_ok.stderr)
        self.assertEqual(proc_ok.stderr, "")

    def test_stop_diff_mode_exits_0_clean_and_2_on_diff_violations(self) -> None:
        # Clean repo with no changes -> exit 0
        proc_empty = self._run_hook()
        self.assertEqual(proc_empty.returncode, 0, msg=proc_empty.stderr)

        # Clean edit to src/app.py -> exit 0
        (self.repo / "src" / "app.py").write_text(
            "def add(a: int, b: int) -> int:\n    return int(a) + int(b)\n",
            encoding="utf-8",
        )
        proc_clean = self._run_hook()
        self.assertEqual(proc_clean.returncode, 0, msg=proc_clean.stderr)

        # Unstaged stub violation -> exit 2 with remediation on stderr
        (self.repo / "src" / "app.py").write_text(
            "def add(a: int, b: int) -> int:\n"
            "    # TODO: handle overflow\n"
            "    return a + b\n",
            encoding="utf-8",
        )
        proc_stub = self._run_hook()
        self.assertEqual(proc_stub.returncode, 2)
        self.assertIn("DIFF-STUB-TODO", proc_stub.stderr)

        # Restore src/app.py and stage an unauthorized tests/ edit -> exit 2
        _git(self.repo, "checkout", "--", "src/app.py")
        (self.repo / "tests" / "test_app.py").write_text(
            "def test_add():\n    assert 2 + 2 == 4\n",
            encoding="utf-8",
        )
        _git(self.repo, "add", "tests/test_app.py")
        proc_test_block = self._run_hook()
        self.assertEqual(proc_test_block.returncode, 2)
        self.assertIn("DIFF-UNAUTHORIZED-TEST-EDIT", proc_test_block.stderr)

        # Same staged test edit passes when --allow-test-edit is set -> exit 0
        proc_test_ok = self._run_hook("--allow-test-edit")
        self.assertEqual(proc_test_ok.returncode, 0, msg=proc_test_ok.stderr)

    def test_stop_diff_mode_works_on_unborn_repo_without_head(self) -> None:
        with tempfile.TemporaryDirectory() as unborn_tmp:
            unborn = Path(unborn_tmp)
            _git(unborn, "init", "-q")
            (unborn / "src").mkdir()
            (unborn / "src" / "stub.py").write_text(
                "def pending():\n    raise NotImplementedError()\n",
                encoding="utf-8",
            )
            _git(unborn, "add", "src/stub.py")
            env = os.environ.copy()
            env.pop("ANTI_SLOP_ALLOW_TEST_EDIT", None)
            env.pop("ANTI_SLOP_BENCHMARK_SUBJECT", None)
            proc = subprocess.run(
                [sys.executable, "-B", str(HOOK_SCRIPT), "--repo-root", str(unborn)],
                input="",
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertIn("DIFF-STUB-NOT-IMPLEMENTED", proc.stderr)

    def test_antigravity_pretooluse_and_stop_json_stdout_contract(self) -> None:
        with tempfile.TemporaryDirectory() as outside_tmp:
            outside = Path(outside_tmp)

            # PreToolUse deny via Antigravity toolCall schema (auto-detected & workspacePaths resolution)
            deny_payload = json.dumps({
                "hookEventName": "PreToolUse",
                "workspacePaths": [str(self.repo)],
                "toolCall": {
                    "id": "toolu_01",
                    "name": "edit_file",
                    "args": {"Path": str(self.repo / "tests" / "test_app.py")},
                },
            })
            proc_deny = self._run_hook(
                "--stdin-tool-json",
                stdin_text=deny_payload,
                include_repo_root=False,
                cwd=outside,
            )
            self.assertEqual(proc_deny.returncode, 0, msg=proc_deny.stderr)
            out_deny = json.loads(proc_deny.stdout)
            self.assertEqual(out_deny["decision"], "deny")
            self.assertIn("DIFF-UNAUTHORIZED-TEST-EDIT", out_deny["reason"])

            # PreToolUse allow on production file and on read_file under tests/
            for name, target in (
                ("edit_file", str(self.repo / "src" / "app.py")),
                ("read_file", str(self.repo / "tests" / "test_app.py")),
            ):
                with self.subTest(tool=name, target=target):
                    allow_payload = json.dumps({
                        "hookEventName": "PreToolUse",
                        "cwd": str(self.repo),
                        "toolCall": {"id": "toolu_02", "name": name, "args": {"Path": target}},
                    })
                    proc_allow = self._run_hook(
                        "--harness",
                        "antigravity",
                        "--stdin-tool-json",
                        stdin_text=allow_payload,
                        include_repo_root=False,
                        cwd=outside,
                    )
                    self.assertEqual(proc_allow.returncode, 0, msg=proc_allow.stderr)
                    self.assertEqual(json.loads(proc_allow.stdout), {"decision": "allow"})

            # Stop allow on clean repo (resolving workspace from stdin cwd when hook cwd is outside)
            stop_payload = json.dumps({
                "hookEventName": "Stop",
                "cwd": str(self.repo),
                "terminationReason": "NO_TOOL_CALL",
                "continuationActive": False,
            })
            proc_clean = self._run_hook(
                "--harness",
                "antigravity",
                stdin_text=stop_payload,
                include_repo_root=False,
                cwd=outside,
            )
            self.assertEqual(proc_clean.returncode, 0, msg=proc_clean.stderr)
            self.assertEqual(json.loads(proc_clean.stdout), {"decision": "allow"})

            # Dirty repo with debugger leftover -> Antigravity Stop returns decision="continue" (exit 0)
            (self.repo / "src" / "app.py").write_text(
                "def add(a: int, b: int) -> int:\n    breakpoint()\n    return a + b\n",
                encoding="utf-8",
            )
            proc_cont = self._run_hook(
                "--harness",
                "auto",
                stdin_text=stop_payload,
                include_repo_root=False,
                cwd=outside,
            )
            self.assertEqual(proc_cont.returncode, 0, msg=proc_cont.stderr)
            out_cont = json.loads(proc_cont.stdout)
            self.assertEqual(out_cont["decision"], "continue")
            self.assertIn("DIFF-DEBUG-LEFTOVER", out_cont["reason"])

            # Anti-loop guard: continuationActive=True -> immediate allow despite dirty repo
            loop_payload = json.dumps({
                "hookEventName": "Stop",
                "cwd": str(self.repo),
                "terminationReason": "NO_TOOL_CALL",
                "continuationActive": True,
            })
            proc_loop = self._run_hook(
                "--harness",
                "antigravity",
                stdin_text=loop_payload,
                include_repo_root=False,
                cwd=outside,
            )
            self.assertEqual(proc_loop.returncode, 0, msg=proc_loop.stderr)
            self.assertEqual(json.loads(proc_loop.stdout), {"decision": "allow"})

            # Anti-loop guard: non-NO_TOOL_CALL terminationReason -> immediate allow despite dirty repo
            cancel_payload = json.dumps({
                "hookEventName": "Stop",
                "cwd": str(self.repo),
                "terminationReason": "USER_CANCELED",
                "continuationActive": False,
            })
            proc_cancel = self._run_hook(
                "--harness",
                "antigravity",
                stdin_text=cancel_payload,
                include_repo_root=False,
                cwd=outside,
            )
            self.assertEqual(proc_cancel.returncode, 0, msg=proc_cancel.stderr)
            self.assertEqual(json.loads(proc_cancel.stdout), {"decision": "allow"})

    def test_claude_stop_hook_active_loop_guard_and_non_git_noop(self) -> None:
        # Make repo dirty with an objective defect
        (self.repo / "src" / "app.py").write_text(
            "def add(a: int, b: int) -> int:\n    breakpoint()\n    return a + b\n",
            encoding="utf-8",
        )
        # Without stop_hook_active, Claude/Codex blocks with exit 2
        proc_block = self._run_hook(
            "--harness",
            "claude",
            stdin_text=json.dumps({"cwd": str(self.repo), "stop_hook_active": False}),
            include_repo_root=False,
        )
        self.assertEqual(proc_block.returncode, 2)
        self.assertIn("DIFF-DEBUG-LEFTOVER", proc_block.stderr)

        # With stop_hook_active=True, Claude/Codex allows stop immediately (exit 0)
        proc_guard = self._run_hook(
            "--harness",
            "claude",
            stdin_text=json.dumps({"cwd": str(self.repo), "stop_hook_active": True}),
            include_repo_root=False,
        )
        self.assertEqual(proc_guard.returncode, 0, msg=proc_guard.stderr)
        self.assertEqual(proc_guard.stderr, "")

        # Non-git directory gracefully no-ops (exit 0; Antigravity emits allow JSON)
        with tempfile.TemporaryDirectory() as nongit_tmp:
            proc_claude = self._run_hook(
                "--harness",
                "claude",
                stdin_text=json.dumps({"cwd": nongit_tmp}),
                include_repo_root=False,
            )
            self.assertEqual(proc_claude.returncode, 0, msg=proc_claude.stderr)
            self.assertEqual(proc_claude.stdout, "")
            self.assertEqual(proc_claude.stderr, "")

            proc_agy = self._run_hook(
                "--harness",
                "antigravity",
                stdin_text=json.dumps({
                    "hookEventName": "Stop",
                    "cwd": nongit_tmp,
                    "terminationReason": "NO_TOOL_CALL",
                }),
                include_repo_root=False,
            )
            self.assertEqual(proc_agy.returncode, 0, msg=proc_agy.stderr)
            self.assertEqual(json.loads(proc_agy.stdout), {"decision": "allow"})

    def test_benchmark_subject_bypass_and_no_budget_flag(self) -> None:
        # Dirty repo with debugger leftover + skip decorator in tests/
        (self.repo / "src" / "app.py").write_text(
            "def add(a: int, b: int) -> int:\n    breakpoint()\n    return a + b\n",
            encoding="utf-8",
        )
        (self.repo / "tests" / "test_app.py").write_text(
            "import unittest\n\n@unittest.skip('temporary')\ndef test_add():\n    assert 1 + 1 == 2\n",
            encoding="utf-8",
        )

        # Env bypass: ANTI_SLOP_BENCHMARK_SUBJECT=1 no-ops cleanly for Claude & Antigravity
        proc_env_claude = self._run_hook(
            "--harness",
            "claude",
            env_extra={"ANTI_SLOP_BENCHMARK_SUBJECT": "1"},
        )
        self.assertEqual(proc_env_claude.returncode, 0, msg=proc_env_claude.stderr)
        self.assertEqual(proc_env_claude.stderr, "")

        proc_env_agy = self._run_hook(
            "--harness",
            "antigravity",
            env_extra={"ANTI_SLOP_BENCHMARK_SUBJECT": "1"},
        )
        self.assertEqual(proc_env_agy.returncode, 0, msg=proc_env_agy.stderr)
        self.assertEqual(json.loads(proc_env_agy.stdout), {"decision": "allow"})

        # Directory-prefix bypass: antislop_* temp workspace no-ops cleanly even when dirty
        with tempfile.TemporaryDirectory(prefix="antislop_subject_") as bench_tmp:
            bench_dir = Path(bench_tmp)
            _git(bench_dir, "init", "-q")
            _git(bench_dir, "config", "user.email", "test@example.com")
            _git(bench_dir, "config", "user.name", "Test User")
            (bench_dir / "app.py").write_text("x = 1\n", encoding="utf-8")
            _git(bench_dir, "add", ".")
            _git(bench_dir, "commit", "-q", "-m", "init")
            (bench_dir / "app.py").write_text("breakpoint()\n", encoding="utf-8")

            proc_dir = self._run_hook(
                "--harness",
                "claude",
                stdin_text=json.dumps({"cwd": str(bench_dir)}),
                include_repo_root=False,
            )
            self.assertEqual(proc_dir.returncode, 0, msg=proc_dir.stderr)
            self.assertEqual(proc_dir.stderr, "")

            proc_dir_agy = self._run_hook(
                "--harness",
                "antigravity",
                stdin_text=json.dumps({
                    "hookEventName": "Stop",
                    "workspacePaths": [str(bench_dir)],
                    "terminationReason": "NO_TOOL_CALL",
                }),
                include_repo_root=False,
            )
            self.assertEqual(proc_dir_agy.returncode, 0, msg=proc_dir_agy.stderr)
            self.assertEqual(json.loads(proc_dir_agy.stdout), {"decision": "allow"})

        # --no-budget + --allow-test-edit still blocks objective defects (DIFF-DEBUG-LEFTOVER & DIFF-TEST-SKIP)
        proc_obj = self._run_hook("--harness", "codex", "--allow-test-edit", "--no-budget")
        self.assertEqual(proc_obj.returncode, 2)
        self.assertIn("DIFF-DEBUG-LEFTOVER", proc_obj.stderr)
        self.assertIn("DIFF-TEST-SKIP", proc_obj.stderr)

        # --no-budget passes a clean large refactor (>400 net LOC) that default budget rejects
        _git(self.repo, "checkout", "--", "tests/test_app.py")
        large_clean = "\n".join(f"VAL_{i} = {i}" for i in range(450)) + "\n"
        (self.repo / "src" / "app.py").write_text(large_clean, encoding="utf-8")
        proc_default_budget = self._run_hook("--harness", "claude")
        self.assertEqual(proc_default_budget.returncode, 2)
        self.assertIn("DIFF-MAX-NET-LOC", proc_default_budget.stderr)

        proc_no_budget = self._run_hook("--harness", "claude", "--no-budget")
        self.assertEqual(proc_no_budget.returncode, 0, msg=proc_no_budget.stderr)

    def test_stop_hook_auto_enforces_approved_learned_rules_and_noops_without_store(self) -> None:
        learn = _load_module("learn_hooks_test", "gates/learn.py")

        # 1. Without .anti-slop/learned/rules.json, currency float edit passes cleanly (fail-safe no-op).
        (self.repo / "src" / "app.py").write_text(
            "def add(a: int, b: int) -> int:\n"
            "    total = float(cents) / 100.0\n"
            "    return int(total) + a + b\n",
            encoding="utf-8",
        )
        proc_no_store = self._run_hook("--harness", "claude", "--no-budget")
        self.assertEqual(proc_no_store.returncode, 0, msg=proc_no_store.stderr)

        # 2. Capture, propose, and verify a rule (NOT YET approved) -> must NOT block.
        store_path = learn.default_store_path(self.repo)
        _git(self.repo, "checkout", "--", "src/app.py")
        entry = learn.capture_pattern(
            store_path,
            title="Float math on currency",
            bad_example="total = float(cents) / 100.0",
            desired_outcome="Keep currency math in integer cents or Decimal.",
            valid_neighbouring_case="seconds = float(elapsed_ms) / 1000.0",
        )
        learn.propose_prevention(
            store_path,
            entry["id"],
            layer="deterministic_check",
            severity="error",
            file_glob="*.py",
            pattern=r"\bfloat\s*\(\s*\w*(?:cent|price|amount)\w*\s*\)",
            remediation="Use integer cents or Decimal for currency math.",
            retirement_trigger="Retire once static Cents typing enforces integer-only math.",
        )
        verified = learn.verify_rule(store_path, entry["id"], repo_root=self.repo)
        self.assertEqual(verified["status"], "verified")

        (self.repo / "src" / "app.py").write_text(
            "def add(a: int, b: int) -> int:\n"
            "    total = float(cents) / 100.0\n"
            "    return int(total) + a + b\n",
            encoding="utf-8",
        )
        proc_unapproved = self._run_hook("--harness", "claude", "--no-budget")
        self.assertEqual(proc_unapproved.returncode, 0, msg=proc_unapproved.stderr)

        # 3. Approve as a human -> live Stop hook automatically blocks both Claude (exit 2) and Antigravity (continue).
        learn.approve_rule(store_path, entry["id"], approved_by="maintainer")

        proc_claude_block = self._run_hook("--harness", "claude", "--no-budget")
        self.assertEqual(proc_claude_block.returncode, 2)
        self.assertIn("LEARNED-L-001", proc_claude_block.stderr)

        proc_agy_block = self._run_hook(
            "--harness",
            "antigravity",
            "--no-budget",
            stdin_text=json.dumps({
                "hookEventName": "Stop",
                "cwd": str(self.repo),
                "terminationReason": "NO_TOOL_CALL",
                "continuationActive": False,
            }),
            include_repo_root=False,
        )
        self.assertEqual(proc_agy_block.returncode, 0, msg=proc_agy_block.stderr)
        agy_out = json.loads(proc_agy_block.stdout)
        self.assertEqual(agy_out["decision"], "continue")
        self.assertIn("LEARNED-L-001", agy_out["reason"])

        # 4. Valid neighbouring code passes cleanly under the approved rule.
        (self.repo / "src" / "app.py").write_text(
            "def add(a: int, b: int) -> int:\n"
            "    seconds = float(elapsed_ms) / 1000.0\n"
            "    return int(seconds) + a + b\n",
            encoding="utf-8",
        )
        proc_valid = self._run_hook("--harness", "claude", "--no-budget")
        self.assertEqual(proc_valid.returncode, 0, msg=proc_valid.stderr)

        # 5. Retiring the rule stops enforcement cleanly.
        learn.retire_rule(store_path, entry["id"], reason="Superseded by static Cents typing.")
        (self.repo / "src" / "app.py").write_text(
            "def add(a: int, b: int) -> int:\n"
            "    total = float(cents) / 100.0\n"
            "    return int(total) + a + b\n",
            encoding="utf-8",
        )
        proc_retired = self._run_hook("--harness", "claude", "--no-budget")
        self.assertEqual(proc_retired.returncode, 0, msg=proc_retired.stderr)


class HookExamplesIntegrityTests(unittest.TestCase):
    def test_example_hook_json_configs_are_valid_and_wire_wrapper(self) -> None:
        # 1. Claude Code example schema
        claude_data = json.loads(
            (REPO_ROOT / "gates/hooks/claude-settings.example.json").read_text(encoding="utf-8")
        )
        self.assertIn("hooks", claude_data)
        claude_hooks = claude_data["hooks"]
        self.assertIn("PreToolUse", claude_hooks)
        self.assertIn("Stop", claude_hooks)
        claude_pre_cmds = [
            h["command"]
            for entry in claude_hooks["PreToolUse"]
            for h in entry.get("hooks", [])
        ]
        claude_stop_cmds = [
            h["command"]
            for entry in claude_hooks["Stop"]
            for h in entry.get("hooks", [])
        ]
        self.assertTrue(
            any("gates/hooks/run_diff_gate_hook.py" in c and "--stdin-tool-json" in c for c in claude_pre_cmds),
            msg=claude_pre_cmds,
        )
        self.assertTrue(
            any("gates/hooks/run_diff_gate_hook.py" in c for c in claude_stop_cmds),
            msg=claude_stop_cmds,
        )

        # 2. Antigravity verified schema: named top-level hook key, grouped PreToolUse, flat Stop array
        agy_data = json.loads(
            (REPO_ROOT / "gates/hooks/antigravity-hooks.example.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("hooks", agy_data)
        self.assertIn("anti-slop-diff-gate", agy_data)
        agy_hook = agy_data["anti-slop-diff-gate"]
        self.assertIn("PreToolUse", agy_hook)
        self.assertIn("Stop", agy_hook)

        agy_pre_cmds = [
            h["command"]
            for group in agy_hook["PreToolUse"]
            for h in group.get("hooks", [])
        ]
        self.assertTrue(
            any(
                "gates/hooks/run_diff_gate_hook.py" in c
                and "--stdin-tool-json" in c
                and "--harness antigravity" in c
                for c in agy_pre_cmds
            ),
            msg=agy_pre_cmds,
        )

        # Antigravity Stop is a flat list of handler objects (no nested "hooks" wrapper)
        self.assertIsInstance(agy_hook["Stop"], list)
        self.assertGreater(len(agy_hook["Stop"]), 0)
        for handler in agy_hook["Stop"]:
            self.assertNotIn("hooks", handler)
            self.assertEqual(handler.get("type"), "command")
        agy_stop_cmds = [h["command"] for h in agy_hook["Stop"]]
        self.assertTrue(
            any(
                "gates/hooks/run_diff_gate_hook.py" in c and "--harness antigravity" in c
                for c in agy_stop_cmds
            ),
            msg=agy_stop_cmds,
        )

    def test_hooks_markdown_docs_pass_diff_check_and_document_exit_2_and_codex_gap(self) -> None:
        hook_docs = [
            "gates/hooks/README.md",
            "gates/hooks/codex-execpolicy.example.md",
            "gates/hooks/run_diff_gate_hook.py",
        ]
        res = diff_check.check_files(hook_docs, repo_root=REPO_ROOT)
        self.assertTrue(res["ok"], msg=res["errors"])

        readme_text = (REPO_ROOT / "gates/hooks/README.md").read_text(encoding="utf-8")
        self.assertIn("exit `2`", readme_text.lower())

        codex_text = (REPO_ROOT / "gates/hooks/codex-execpolicy.example.md").read_text(encoding="utf-8")
        self.assertIn("execpolicy", codex_text)
        self.assertIn("Stop", codex_text)


class ApiChecksContextHygieneTests(unittest.TestCase):
    def test_claude_missing_tool_clear_warns_on_long_horizon_and_passes_valid_neighbours(self) -> None:
        for model in ("claude-opus-5-5", "claude-fable-5-2"):
            for trigger_cfg in (
                {"long_horizon": True},
                {"max_turns": 10},
                {"max_turns": 15, "context_management": {"edits": []}},
            ):
                with self.subTest(model=model, trigger=trigger_cfg):
                    cfg = {
                        "model": model,
                        "thinking": {"type": "adaptive"},
                        "output_config": {"effort": "high"},
                        **trigger_cfg,
                    }
                    res = api_checks.validate_config(cfg)
                    self.assertTrue(res["ok"], msg=res["errors"])
                    self.assertEqual(res["errors"], [])
                    self.assertIn("CLAUDE-MISSING-TOOL-CLEAR", _codes(res["warnings"]))
                    warn = next(w for w in res["warnings"] if w["code"] == "CLAUDE-MISSING-TOOL-CLEAR")
                    self.assertIn("2508.21433", warn["message"])
                    self.assertIn("+29%", warn["message"])
                    self.assertIn("+39%", warn["message"])

            # Valid neighbouring cases: short session or configured tool clearing / observation masking
            for clean_cfg in (
                {"max_turns": 5},
                {
                    "long_horizon": True,
                    "context_management": {"edits": [{"type": "clear_tool_uses_20250919"}]},
                },
                {"max_turns": 20, "clear_tool_uses": True},
                {"long_horizon": True, "observation_masking": True},
            ):
                with self.subTest(model=model, clean=clean_cfg):
                    cfg = {
                        "model": model,
                        "thinking": {"type": "adaptive"},
                        "output_config": {"effort": "high"},
                        **clean_cfg,
                    }
                    res = api_checks.validate_config(cfg)
                    self.assertTrue(res["ok"], msg=res["errors"])
                    self.assertNotIn("CLAUDE-MISSING-TOOL-CLEAR", _codes(res["warnings"]))

        # Non-Claude models do not trigger CLAUDE-MISSING-TOOL-CLEAR
        res_gpt = api_checks.validate_config({
            "model": "gpt-6.2-astra",
            "reasoning": {"effort": "medium"},
            "long_horizon": True,
            "max_turns": 20,
        })
        self.assertTrue(res_gpt["ok"])
        self.assertNotIn("CLAUDE-MISSING-TOOL-CLEAR", _codes(res_gpt["warnings"]))

    def test_harness_lossy_summary_only_warns_for_all_models_and_passes_valid_neighbours(self) -> None:
        base_configs = {
            "gpt-6.2-astra": {"model": "gpt-6.2-astra", "reasoning": {"effort": "medium"}},
            "gpt-6.2-sol": {"model": "gpt-6.2-sol", "reasoning": {"effort": "medium"}},
            "claude-opus-5-5": {"model": "claude-opus-5-5", "thinking": {"type": "adaptive"}},
            "claude-fable-5-2": {"model": "claude-fable-5-2", "thinking": {"type": "adaptive"}},
            "gemini-4-neon": {"model": "gemini-4-neon", "thinking_level": "HIGH"},
        }
        for model, base in base_configs.items():
            with self.subTest(model=model, mode="warn"):
                res = api_checks.validate_config(
                    {**base, "compaction_strategy": "summarize_only"},
                    strict=True,
                )
                self.assertTrue(res["ok"], msg=res["errors"])
                self.assertEqual(res["errors"], [])
                self.assertIn("HARNESS-LOSSY-SUMMARY-ONLY", _codes(res["warnings"]))
                warn = next(w for w in res["warnings"] if w["code"] == "HARNESS-LOSSY-SUMMARY-ONLY")
                self.assertIn("2508.21433", warn["message"])

            # Valid neighbouring cases: paired with observation_masking, checkpoint_reset, or hybrid strategy
            for safe_extra in (
                {"compaction_strategy": "summarize_only", "observation_masking": True},
                {"compaction_strategy": "summarize_only", "checkpoint_reset": True},
                {"compaction_strategy": "observation_masking"},
                {"compaction_strategy": "hybrid"},
            ):
                with self.subTest(model=model, safe=safe_extra):
                    res = api_checks.validate_config({**base, **safe_extra})
                    self.assertTrue(res["ok"], msg=res["errors"])
                    self.assertNotIn("HARNESS-LOSSY-SUMMARY-ONLY", _codes(res["warnings"]))


class ModelDeltasScopingTests(unittest.TestCase):
    def test_r7_model_delta_refinements_in_place(self) -> None:
        data = json.loads((REPO_ROOT / "gates/model_deltas.json").read_text(encoding="utf-8"))
        opus_rules = {r["id"]: r for r in data["models"]["claude-opus-5-5"]["rules"]}
        neon_rules = {r["id"]: r for r in data["models"]["gemini-4-neon"]["rules"]}

        self.assertIn("length-bounded", opus_rules["D-OPU-1"]["rule"])
        for phrase in ("PR description", "review comment", "Slack reply", "chatbot closers", "decorative emojis"):
            self.assertIn(phrase, opus_rules["D-OPU-4"]["rule"])
        self.assertIn("uncapped", neon_rules["D-NEO-2"]["rule"].lower())
        self.assertIn("March 2026", neon_rules["D-NEO-2"]["rule"])


if __name__ == "__main__":
    unittest.main()
