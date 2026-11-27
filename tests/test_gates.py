"""Comprehensive stdlib-only tests for Layer-1 gates (gates/api_checks.py,
gates/diff_check.py, gates/model_deltas.json, gates/vale/, and gates/ci-ratchet.yml).

Every gate rule is tested against both its reproduced failure case and at least
one valid neighbouring case to guard against overbroad rules or false positives.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, rel_path: str):
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


api_checks = _load_module("api_checks", "gates/api_checks.py")
diff_check = _load_module("diff_check", "gates/diff_check.py")


def _codes(items) -> set:
    return {item["code"] for item in items}


def _parse_simple_vale_yaml(path: Path) -> dict:
    """Minimal stdlib parser for Vale rule YAML files (scalars + list fields)."""
    data: dict = {}
    current_list_key = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_list_key is not None:
            val = stripped[2:].strip()
            if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
                val = val[1:-1].replace("''", "'")
            data[current_list_key].append(val)
            continue
        if ":" in raw_line and not raw_line.startswith(" "):
            key, rest = raw_line.split(":", 1)
            key = key.strip()
            rest = rest.strip()
            if not rest:
                data[key] = []
                current_list_key = key
            else:
                if (rest.startswith("'") and rest.endswith("'")) or (rest.startswith('"') and rest.endswith('"')):
                    rest = rest[1:-1].replace("''", "'")
                data[key] = rest
                current_list_key = None
    return data


class ApiChecksGPT62Tests(unittest.TestCase):
    def test_valid_neighbouring_concise_gpt62_astra_and_sol_configs(self) -> None:
        astra_cfg = {
            "model": "gpt-6.2-astra",
            "reasoning": {"effort": "medium"},
            "input": [
                {
                    "role": "developer",
                    "content": (
                        "Put the decision in the first paragraph, preserve material caveats, "
                        "and end with a Blockers & Flaws section."
                    ),
                },
                {"role": "user", "content": "Audit the retry loop."},
            ],
            "thread_models": ["gpt-6.2-astra", "gpt-6.2-astra"],
            "pr_comment_cap": 10,
        }
        snapshot = copy.deepcopy(astra_cfg)
        res = api_checks.validate_config(astra_cfg)
        self.assertTrue(res["ok"])
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["warnings"], [])
        self.assertEqual(astra_cfg, snapshot)  # Never mutates input

        sol_pr_cfg = {
            "model": "gpt-6.2-sol",
            "reasoning": {"effort": "low"},
            "task_type": "pr_review",
            "pr_comment_cap": 8,
            "input": [{"role": "developer", "content": "Flag only high-severity defects."}],
        }
        sol_res = api_checks.validate_config(sol_pr_cfg)
        self.assertTrue(sol_res["ok"])
        self.assertEqual(sol_res["errors"], [])
        self.assertEqual(sol_res["warnings"], [])

        # Valid neighbouring cases: GPT-6.2 xhigh and light effort aliases pass cleanly.
        for model, effort in (("gpt-6.2-astra", "xhigh"), ("gpt-6.2-sol", "light")):
            with self.subTest(model=model, effort=effort):
                eff_res = api_checks.validate_config({
                    "model": model,
                    "reasoning": {"effort": effort},
                })
                self.assertTrue(eff_res["ok"], msg=eff_res["errors"])
                self.assertEqual(eff_res["errors"], [])
                self.assertEqual(eff_res["warnings"], [])

    def test_gpt62_rejects_effort_none_and_flex_service_tier(self) -> None:
        for model in ("gpt-6.2-astra", "gpt-6.2-sol"):
            with self.subTest(model=model):
                res = api_checks.validate_config({
                    "model": model,
                    "reasoning": {"effort": "none"},
                    "service_tier": "flex",
                })
                self.assertFalse(res["ok"])
                self.assertIn("GPT-EFFORT-NONE", _codes(res["errors"]))
                self.assertIn("GPT-FLEX-TIER", _codes(res["errors"]))

    def test_gpt62_rejects_top_level_instructions_cache_break(self) -> None:
        res = api_checks.validate_config({
            "model": "gpt-6.2-astra",
            "reasoning": {"effort": "medium"},
            "instructions": "You are a careful software reviewer.",
        })
        self.assertFalse(res["ok"])
        self.assertIn("GPT-INSTRUCTIONS-CACHE", _codes(res["errors"]))

    def test_gpt62_rejects_banned_concise_phrases(self) -> None:
        for phrase in ("Please be concise in every reply.", "Always keep it short."):
            with self.subTest(phrase=phrase):
                res = api_checks.validate_config({
                    "model": "gpt-6.2-sol",
                    "reasoning": {"effort": "medium"},
                    "input": [
                        {"role": "developer", "content": [{"type": "input_text", "text": phrase}]}
                    ],
                })
                self.assertFalse(res["ok"])
                self.assertIn("GPT-BANNED-CONCISE-PROMPT", _codes(res["errors"]))

    def test_gpt62_rejects_mid_thread_astra_sol_swap(self) -> None:
        res_a = api_checks.validate_config({
            "model": "gpt-6.2-sol",
            "previous_model": "gpt-6.2-astra",
            "reasoning": {"effort": "medium"},
        })
        self.assertFalse(res_a["ok"])
        self.assertIn("GPT-MID-THREAD-SWAP", _codes(res_a["errors"]))

        res_b = api_checks.validate_config({
            "model": "gpt-6.2-astra",
            "thread_models": ["gpt-6.2-sol", "gpt-6.2-astra"],
            "reasoning": {"effort": "high"},
        })
        self.assertFalse(res_b["ok"])
        self.assertIn("GPT-MID-THREAD-SWAP", _codes(res_b["errors"]))

    def test_gpt62_sol_pr_review_warnings(self) -> None:
        res = api_checks.validate_config({
            "model": "gpt-6.2-sol",
            "reasoning": {"effort": "high"},
            "task_type": "pr_review",
            "pr_comment_cap": 15,
        })
        self.assertTrue(res["ok"])
        self.assertEqual(res["errors"], [])
        warn_codes = _codes(res["warnings"])
        self.assertIn("GPT-SOL-PR-HIGH-EFFORT", warn_codes)
        self.assertIn("GPT-PR-COMMENT-CAP", warn_codes)


class ApiChecksClaudeTests(unittest.TestCase):
    def test_valid_neighbouring_opus_and_fable_configs(self) -> None:
        opus_cfg = {
            "model": "claude-opus-5-5",
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "high"},
            "previous_thinking_blocks": [{"id": "t1", "signature": "sig1"}],
            "current_thinking_blocks": [
                {"id": "t1", "signature": "sig1"},
                {"id": "t2", "signature": "sig2"},
            ],
            "claude_md": (
                "# Repo rules\n"
                "NEVER edit files under tests/ unless --allow-test-edit is set.\n"
                "ALWAYS run unit tests except when editing docs-only files.\n"
                "```text\n"
                "ALWAYS fail inside code fence example.\n"
                "```\n"
            ),
        }
        res_opus = api_checks.validate_config(opus_cfg)
        self.assertTrue(res_opus["ok"])
        self.assertEqual(res_opus["errors"], [])
        self.assertEqual(res_opus["warnings"], [])

        # Valid neighbouring case: Fable 5.2 with effort=max on SINGLE-TURN call,
        # concurrent_subagents=3, normal response model.
        fable_single = {
            "model": "claude-fable-5-2",
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "max"},
            "multi_turn": False,
            "concurrent_subagents": 3,
            "response": {"model": "claude-fable-5-2", "stop_reason": "end_turn"},
        }
        res_fable = api_checks.validate_config(fable_single)
        self.assertTrue(res_fable["ok"])
        self.assertEqual(res_fable["errors"], [])
        self.assertEqual(res_fable["warnings"], [])

    def test_claude_rejects_disabled_thinking_and_legacy_budget_tokens(self) -> None:
        for model in ("claude-opus-5-5", "claude-fable-5-2"):
            with self.subTest(model=model):
                res = api_checks.validate_config({
                    "model": model,
                    "thinking": {"type": "disabled", "budget_tokens": 4096},
                })
                self.assertFalse(res["ok"])
                err_codes = _codes(res["errors"])
                self.assertIn("CLAUDE-THINKING-DISABLED", err_codes)
                self.assertIn("CLAUDE-LEGACY-BUDGET-TOKENS", err_codes)

    def test_claude_rejects_non_append_only_thinking_mutations(self) -> None:
        res_flag = api_checks.validate_config({
            "model": "claude-opus-5-5",
            "thinking_blocks_append_only": False,
        })
        self.assertFalse(res_flag["ok"])
        self.assertIn("CLAUDE-THINKING-MUTATION", _codes(res_flag["errors"]))

        res_prefix = api_checks.validate_config({
            "model": "claude-fable-5-2",
            "previous_thinking_blocks": [{"id": "t1", "text": "orig"}],
            "current_thinking_blocks": [{"id": "t1", "text": "edited"}],
        })
        self.assertFalse(res_prefix["ok"])
        self.assertIn("CLAUDE-THINKING-MUTATION", _codes(res_prefix["errors"]))

    def test_fable_rejects_max_effort_in_multi_turn_loop_and_subagent_cap(self) -> None:
        for flag in ("multi_turn", "multi_turn_loop"):
            with self.subTest(flag=flag):
                res = api_checks.validate_config({
                    "model": "claude-fable-5-2",
                    "output_config": {"effort": "max"},
                    flag: True,
                    "concurrent_subagents": 4,
                })
                self.assertFalse(res["ok"])
                err_codes = _codes(res["errors"])
                self.assertIn("FABLE-MAX-EFFORT-LOOP", err_codes)
                self.assertIn("FABLE-SUBAGENT-CAP", err_codes)

    def test_fable_critical_error_on_silent_downgrade_or_refusal_fallback(self) -> None:
        cases = [
            {
                "model": "claude-fable-5-2",
                "response": {"model": "claude-fable-5-2", "stop_reason": "model_refusal_fallback"},
            },
            {
                "model": "claude-fable-5-2",
                "response": {"model": "claude-opus-4-8", "stop_reason": "end_turn"},
            },
            {
                "model": "claude-fable-5-2",
                "response_model": "claude-opus-5",
            },
        ]
        for cfg in cases:
            with self.subTest(cfg=cfg):
                res = api_checks.validate_config(cfg)
                self.assertFalse(res["ok"])
                critical = [e for e in res["errors"] if e["code"] == "FABLE-SILENT-DOWNGRADE"]
                self.assertEqual(len(critical), 1)
                self.assertEqual(critical[0]["severity"], "critical")

    def test_claude_md_warns_on_unqualified_always_never(self) -> None:
        res = api_checks.validate_config({
            "model": "claude-opus-5-5",
            "claude_md": (
                "ALWAYS rewrite neighboring modules for consistency.\n"
                "NEVER use helper functions.\n"
            ),
        })
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["warnings"]), 2)
        self.assertTrue(all(w["code"] == "CLAUDE-MD-UNQUALIFIED-ABSOLUTE" for w in res["warnings"]))


class ApiChecksNeonTests(unittest.TestCase):
    def test_valid_neighbouring_neon_high_request_with_thought_signatures(self) -> None:
        cfg = {
            "model": "gemini-4-neon",
            "thinking_level": "HIGH",
            "preserve_thought_signatures": True,
            "task_type": "code_review",
            "response_schema": {
                "type": "object",
                "properties": {"auth": {"type": "string"}},
            },
            "contents": [
                {"role": "user", "parts": [{"text": "Review auth.py"}]},
                {
                    "role": "model",
                    "parts": [{"function_call": {"name": "read_file"}, "thought_signature": "sig-abc"}],
                },
            ],
            "usage": {"thoughts_token_count": 1200, "candidates_token_count": 400},
            "ttft_seconds": 18.5,
        }
        res = api_checks.validate_config(cfg)
        self.assertTrue(res["ok"])
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["warnings"], [])

    def test_valid_neighbouring_neon_xhigh_retry_and_low_single_turn(self) -> None:
        retry_res = api_checks.validate_config({
            "model": "gemini-4-neon",
            "thinking_level": "XHIGH",
            "attempt": 2,
            "preserve_thought_signatures": True,
        })
        self.assertTrue(retry_res["ok"])
        self.assertEqual(retry_res["warnings"], [])

        low_single = api_checks.validate_config({
            "model": "gemini-4-neon",
            "thinking_level": "LOW",
            "multi_step": False,
        })
        self.assertTrue(low_single["ok"])
        self.assertEqual(low_single["warnings"], [])

    def test_neon_rejects_thinking_budget_minimal_and_missing_thought_signatures(self) -> None:
        res = api_checks.validate_config({
            "model": "gemini-4-neon",
            "thinking_budget": 2048,
            "thinking_level": "MINIMAL",
            "preserve_thought_signatures": False,
        })
        self.assertFalse(res["ok"])
        err_codes = _codes(res["errors"])
        self.assertIn("NEON-LEGACY-THINKING-BUDGET", err_codes)
        self.assertIn("NEON-THINKING-LEVEL-MINIMAL", err_codes)
        self.assertIn("NEON-THOUGHT-SIGNATURES", err_codes)

        # Structural check: multi-turn function_call lacking thought_signature.
        res_struct = api_checks.validate_config({
            "model": "gemini-4-neon",
            "thinking_level": "HIGH",
            "contents": [
                {"role": "model", "parts": [{"function_call": {"name": "run_tests"}}]}
            ],
        })
        self.assertFalse(res_struct["ok"])
        self.assertIn("NEON-THOUGHT-SIGNATURES", _codes(res_struct["errors"]))

    def test_neon_warnings_and_strict_sampling_params(self) -> None:
        cfg = {
            "model": "gemini-4-neon",
            "thinking_level": "xhigh",
            "attempt": 1,
            "temperature": 0.0,
            "top_p": 0.9,
            "top_k": 40,
            "task_type": "review",
            "usage": {"thoughts_token_count": 5000, "candidates_token_count": 500},
            "ttft_seconds": 52.0,
        }
        res_default = api_checks.validate_config(cfg)
        self.assertTrue(res_default["ok"])
        warn_codes = _codes(res_default["warnings"])
        self.assertIn("NEON-IGNORED-SAMPLING-PARAMS", warn_codes)
        self.assertIn("NEON-XHIGH-ATTEMPT-1", warn_codes)
        self.assertIn("NEON-THINKING-TOKEN-RATIO", warn_codes)
        self.assertIn("NEON-TTFT-HIGH", warn_codes)
        self.assertIn("NEON-MISSING-RESPONSE-SCHEMA", warn_codes)

        res_strict = api_checks.validate_config(cfg, strict=True)
        self.assertFalse(res_strict["ok"])
        self.assertIn("NEON-IGNORED-SAMPLING-PARAMS", _codes(res_strict["errors"]))

        res_low_loop = api_checks.validate_config({
            "model": "gemini-4-neon",
            "thinking_level": "low",
            "multi_step": True,
        })
        self.assertTrue(res_low_loop["ok"])
        self.assertIn("NEON-LOW-MULTI-STEP", _codes(res_low_loop["warnings"]))

    def test_api_checks_cli_exit_codes_and_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ok_file = Path(tmp) / "ok.json"
            bad_file = Path(tmp) / "bad.json"
            ok_file.write_text(json.dumps({
                "model": "gemini-4-neon",
                "thinking_level": "HIGH",
                "preserve_thought_signatures": True,
            }), encoding="utf-8")
            bad_file.write_text(json.dumps({
                "model": "gpt-6.2-astra",
                "reasoning": {"effort": "none"},
            }), encoding="utf-8")

            proc_ok = subprocess.run(
                [sys.executable, "-B", str(REPO_ROOT / "gates/api_checks.py"), "--json", str(ok_file)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc_ok.returncode, 0)
            payload_ok = json.loads(proc_ok.stdout)
            self.assertTrue(payload_ok["ok"])
            self.assertEqual(payload_ok["errors"], [])

            proc_bad = subprocess.run(
                [sys.executable, "-B", str(REPO_ROOT / "gates/api_checks.py"), "--json", str(bad_file)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc_bad.returncode, 1)
            payload_bad = json.loads(proc_bad.stdout)
            self.assertFalse(payload_bad["ok"])
            self.assertIn("GPT-EFFORT-NONE", _codes(payload_bad["errors"]))


class DiffCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "src").mkdir()
        (self.root / "docs").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "src" / "app.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
        (self.root / "docs" / "guide.md").write_text("# Guide\n\nSee `src/app.py`.\n", encoding="utf-8")

    def test_stub_additions_flagged_in_diff_while_deleted_and_abstract_pass_allowed(self) -> None:
        bad_diff = (
            "diff --git a/src/worker.py b/src/worker.py\n"
            "--- /dev/null\n"
            "+++ b/src/worker.py\n"
            "@@ -0,0 +1,11 @@\n"
            "+def fetch():\n"
            "+    # TODO: implement retry\n"
            "+    return None\n"
            "+\n"
            "+def parse():\n"
            "+    # FIXME broken parser\n"
            "+    raise NotImplementedError()\n"
            "+\n"
            "+def sync():\n"
            "+    pass\n"
        )
        res = diff_check.check_diff(bad_diff)
        self.assertFalse(res["ok"])
        codes = _codes(res["errors"])
        self.assertIn("DIFF-STUB-TODO", codes)
        self.assertIn("DIFF-STUB-NOT-IMPLEMENTED", codes)
        self.assertIn("DIFF-STUB-PASS", codes)

        # Valid neighbouring cases:
        # 1) Removed TODO lines do not trigger errors.
        # 2) @abstractmethod / Protocol / custom Exception class with `pass` allowed.
        good_diff = (
            "diff --git a/src/interfaces.py b/src/interfaces.py\n"
            "--- a/src/interfaces.py\n"
            "+++ b/src/interfaces.py\n"
            "@@ -1,4 +1,20 @@\n"
            "-# TODO: clean up legacy stub\n"
            "+from abc import ABC, abstractmethod\n"
            "+from typing import Protocol\n"
            "+\n"
            "+class ValidationError(Exception):\n"
            "+    pass\n"
            "+\n"
            "+class BaseRunner(ABC):\n"
            "+    @abstractmethod\n"
            "+    def run(self) -> None:\n"
            "+        pass\n"
            "+\n"
            "+class Loader(Protocol):\n"
            "+    def load(self, key: str) -> bytes:\n"
            "+        pass\n"
            "+\n"
            "+def real_work(x: int) -> int:\n"
            "+    return x * 2\n"
        )
        res_good = diff_check.check_diff(good_diff)
        self.assertTrue(res_good["ok"], msg=res_good["errors"])

        # Also verify AST file-check mode on the same valid abstract/protocol/exception code.
        iface_file = self.root / "src" / "interfaces.py"
        iface_file.write_text(
            "from abc import ABC, abstractmethod\n"
            "from typing import Protocol\n\n"
            "class ValidationError(Exception):\n"
            "    pass\n\n"
            "class BaseRunner(ABC):\n"
            "    @abstractmethod\n"
            "    def run(self) -> None:\n"
            "        pass\n\n"
            "class Loader(Protocol):\n"
            "    def load(self, key: str) -> bytes:\n"
            "        pass\n",
            encoding="utf-8",
        )
        res_file = diff_check.check_files(["src/interfaces.py"], repo_root=self.root)
        self.assertTrue(res_file["ok"], msg=res_file["errors"])

    def test_stub_false_positive_regressions_empty_subclass_and_prose_todo_mentions(self) -> None:
        # Regression 1 (sdispater/tomlkit hunk-only audit): empty marker/subclass
        # definitions with `pass` (single-line and multi-line headers) must pass
        # in BOTH hunk-only mode (repo_root=None) and disk AST mode.
        subclass_diff = (
            "diff --git a/src/keys.py b/src/keys.py\n"
            "--- /dev/null\n"
            "+++ b/src/keys.py\n"
            "@@ -0,0 +1,9 @@\n"
            "+class StringKey(str):\n"
            "+    pass\n"
            "+\n"
            "+class MultiLineKey(\n"
            "+    str,\n"
            "+):\n"
            "+    pass\n"
            "+\n"
            "+class Sentinel:\n"
            "+    pass\n"
        )
        res_sub_hunk = diff_check.check_diff(subclass_diff, repo_root=None)
        self.assertTrue(res_sub_hunk["ok"], msg=res_sub_hunk["errors"])

        # Non-abstract method `pass` inside a class (including multi-line def) MUST still fail.
        bad_method_diff = (
            "diff --git a/src/keys.py b/src/keys.py\n"
            "--- /dev/null\n"
            "+++ b/src/keys.py\n"
            "@@ -0,0 +1,6 @@\n"
            "+class Worker:\n"
            "+    def run(\n"
            "+        self,\n"
            "+    ) -> None:\n"
            "+        pass\n"
        )
        res_bad_method = diff_check.check_diff(bad_method_diff, repo_root=None)
        self.assertFalse(res_bad_method["ok"])
        self.assertIn("DIFF-STUB-PASS", _codes(res_bad_method["errors"]))

        # Regression 2 (self-repo audit): prose comments mentioning TODO/FIXME and
        # string literals containing TODO/FIXME must not trigger DIFF-STUB-TODO,
        # while actual TODO/FIXME markers in comments still trigger in both modes.
        prose_py = (
            "# 1) Removed TODO lines do not trigger errors.\n"
            "# Document how FIXME markers are stripped from reports.\n"
            'LABEL = "# TODO: example inside Python string"\n'
        )
        prose_py_diff = (
            "diff --git a/src/prose_notes.py b/src/prose_notes.py\n"
            "--- /dev/null\n"
            "+++ b/src/prose_notes.py\n"
            "@@ -0,0 +1,3 @@\n"
            + "".join(f"+{line}\n" for line in prose_py.splitlines())
        )
        self.assertTrue(diff_check.check_diff(prose_py_diff, repo_root=None)["ok"])
        (self.root / "src" / "prose_notes.py").write_text(prose_py, encoding="utf-8")
        self.assertTrue(diff_check.check_files(["src/prose_notes.py"], repo_root=self.root)["ok"])

        prose_ts = (
            "// Verify removed TODO lines are ignored by the scanner.\n"
            'const sample = "TODO: placeholder inside string literal";\n'
            'const fakeComment = "// FIXME: inside string literal";\n'
        )
        prose_ts_diff = (
            "diff --git a/src/prose_notes.ts b/src/prose_notes.ts\n"
            "--- /dev/null\n"
            "+++ b/src/prose_notes.ts\n"
            "@@ -0,0 +1,3 @@\n"
            + "".join(f"+{line}\n" for line in prose_ts.splitlines())
        )
        self.assertTrue(diff_check.check_diff(prose_ts_diff, repo_root=None)["ok"])
        (self.root / "src" / "prose_notes.ts").write_text(prose_ts, encoding="utf-8")
        self.assertTrue(diff_check.check_files(["src/prose_notes.ts"], repo_root=self.root)["ok"])

        # True-positive TODO/FIXME markers in Python and TS comments must still fail.
        for path, line in (
            ("src/real_todo.py", "x = 1  # TODO fix edge case"),
            ("src/real_todo.py", "# Note: FIXME: handle retry"),
            ("src/real_todo.ts", "// TODO: implement retry"),
            ("src/real_todo.ts", "/* FIXME handle timeout */"),
        ):
            real_diff = (
                f"diff --git a/{path} b/{path}\n"
                "--- /dev/null\n"
                f"+++ b/{path}\n"
                "@@ -0,0 +1,1 @@\n"
                f"+{line}\n"
            )
            with self.subTest(path=path, line=line):
                res_real = diff_check.check_diff(real_diff, repo_root=None)
                self.assertFalse(res_real["ok"])
                self.assertIn("DIFF-STUB-TODO", _codes(res_real["errors"]))

    def test_unauthorized_test_edits_blocked_unless_allow_test_edit(self) -> None:
        test_diff = (
            "diff --git a/tests/test_app.py b/tests/test_app.py\n"
            "--- a/tests/test_app.py\n"
            "+++ b/tests/test_app.py\n"
            "@@ -1,2 +1,3 @@\n"
            " def test_ok():\n"
            "+    assert 1 + 1 == 2\n"
        )
        blocked = diff_check.check_diff(test_diff, allow_test_edit=False)
        self.assertFalse(blocked["ok"])
        self.assertIn("DIFF-UNAUTHORIZED-TEST-EDIT", _codes(blocked["errors"]))

        # Valid neighbouring case: --allow-test-edit authorizes test edits.
        allowed = diff_check.check_diff(test_diff, allow_test_edit=True)
        self.assertTrue(allowed["ok"])

    def test_net_loc_and_file_count_budgets(self) -> None:
        # Exceeds max_net_loc=5
        big_loc_diff = (
            "diff --git a/src/big.py b/src/big.py\n"
            "--- /dev/null\n"
            "+++ b/src/big.py\n"
            "@@ -0,0 +1,6 @@\n"
            + "".join(f"+x{i} = {i}\n" for i in range(6))
        )
        res_loc = diff_check.check_diff(big_loc_diff, max_net_loc=5)
        self.assertFalse(res_loc["ok"])
        self.assertIn("DIFF-MAX-NET-LOC", _codes(res_loc["errors"]))

        # Deletion-heavy cleanup (net LOC < 0) passes cleanly.
        cleanup_diff = (
            "diff --git a/src/old.py b/src/old.py\n"
            "--- a/src/old.py\n"
            "+++ b/src/old.py\n"
            "@@ -1,10 +1,2 @@\n"
            + "".join(f"-old_{i} = {i}\n" for i in range(10))
            + "+kept = 1\n+kept_two = 2\n"
        )
        res_clean = diff_check.check_diff(cleanup_diff, max_net_loc=5)
        self.assertTrue(res_clean["ok"])
        self.assertEqual(res_clean["stats"]["net_loc"], -8)

        # Exceeds max_files=2
        many_files_diff = "".join(
            f"diff --git a/src/f{i}.py b/src/f{i}.py\n"
            f"--- /dev/null\n+++ b/src/f{i}.py\n@@ -0,0 +1,1 @@\n+x = {i}\n"
            for i in range(3)
        )
        res_files = diff_check.check_diff(many_files_diff, max_files=2)
        self.assertFalse(res_files["ok"])
        self.assertIn("DIFF-MAX-FILES", _codes(res_files["errors"]))

    def test_chatbot_openers_flagged_outside_fences_and_ignored_inside_fences(self) -> None:
        for opener in (
            "Sure, I updated the parser.",
            "Certainly, here are the changes.",
            "Here is the migration guide.",
            "# RFC: Cache\n\nGreat question! We chose LRU.",
        ):
            with self.subTest(opener=opener):
                errs = diff_check.check_markdown_openers(opener, source="PR.md")
                self.assertEqual(len(errs), 1)
                self.assertEqual(errs[0]["code"], "DIFF-CHATBOT-OPENER")

        # Valid neighbouring cases: chatbot phrase inside fenced code block (``` or ~~~)
        # or clean technical opener.
        fenced_doc = (
            "# Opener Fixtures\n\n"
            "```text\n"
            "Sure, here is a synthetic chatbot reply.\n"
            "Great question!\n"
            "```\n\n"
            "This fixture demonstrates fenced-block exclusion.\n"
        )
        self.assertEqual(diff_check.check_markdown_openers(fenced_doc, source="doc.md"), [])

        tilde_fenced = (
            "~~~markdown\n"
            "Certainly, this is inside a tilde fence.\n"
            "~~~\n\n"
            "Run `python3 scripts/check.py` to verify.\n"
        )
        self.assertEqual(diff_check.check_markdown_openers(tilde_fenced, source="doc.md"), [])

    def test_backticked_local_path_verification_without_false_positives(self) -> None:
        broken_md = (
            "# Notes\n\n"
            "Valid paths: `src/app.py`, `src/app.py:1`, `docs/guide.md#guide`, `docs/`.\n"
            "Non-paths (must NOT flag): `--allow-test-edit`, `tests/test_*.py`, "
            "`reasoning.effort`, `NotImplementedError`, `low/medium`, `pass/fail`, "
            "`https://example.com/foo/bar.md`, `/api/v1/items`, `benchmarks/cases/<id>.json`.\n"
            "```bash\n"
            "cat nonexistent/inside-fence.py\n"
            "```\n"
            "Broken paths: `src/missing.py`, `docs/nope.md`, `ghost_dir/`.\n"
        )
        errs = diff_check.check_markdown_paths(broken_md, repo_root=self.root, source="docs/notes.md")
        flagged = [e["message"] for e in errs]
        self.assertEqual(len(errs), 3, msg=flagged)
        self.assertTrue(any("src/missing.py" in m for m in flagged))
        self.assertTrue(any("docs/nope.md" in m for m in flagged))
        self.assertTrue(any("ghost_dir/" in m for m in flagged))

        # Valid neighbouring case: technical doc with valid paths + flags/globs/identifiers.
        clean_md = (
            "# Architecture\n\n"
            "Run with `--max-net-loc` on `tests/test_*.py`; check `src/app.py` and `docs/guide.md`. "
            "Set `reasoning.effort` to `low/medium`.\n"
        )
        self.assertEqual(
            diff_check.check_markdown_paths(clean_md, repo_root=self.root, source="docs/arch.md"),
            [],
        )

    def test_backticked_path_allows_all_caps_placeholders_and_gitignore_dirs(self) -> None:
        (self.root / ".gitignore").write_text(
            "# local dirs\nruns-local/\nworkspaces/\ndist/\n.venv/\n",
            encoding="utf-8",
        )
        valid_neighbour_md = (
            "# Results\n\n"
            "Store outputs in `results/EXPERIMENT/runs.jsonl` or `configs/ENV_NAME/app.json`, "
            "and keep scratch artifacts in `runs-local/`, `workspaces/`, `dist/`, or `runs-local/tmp.jsonl`.\n"
        )
        self.assertEqual(
            diff_check.check_markdown_paths(valid_neighbour_md, repo_root=self.root, source="results/README.md"),
            [],
        )

        # Real uppercase segments (e.g., ISSUE_TEMPLATE, LICENSE) and unignored missing dirs still fail.
        broken_md = (
            "# Broken\n\n"
            "Missing real paths: `.github/ISSUE_TEMPLATE/missing.md`, `docs/LICENSE`, and `unignored-dir/`.\n"
        )
        errs = diff_check.check_markdown_paths(broken_md, repo_root=self.root, source="docs/broken.md")
        msgs = [e["message"] for e in errs]
        self.assertEqual(len(errs), 3, msg=msgs)
        self.assertTrue(any("ISSUE_TEMPLATE/missing.md" in m for m in msgs))
        self.assertTrue(any("docs/LICENSE" in m for m in msgs))
        self.assertTrue(any("unignored-dir/" in m for m in msgs))

    def test_diff_check_cli_exit_codes_and_json_output(self) -> None:
        diff_file = self.root / "ok.diff"
        diff_file.write_text(
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -1,2 +1,3 @@\n"
            " def add(a: int, b: int) -> int:\n"
            "+    # Return integer sum\n"
            "     return a + b\n",
            encoding="utf-8",
        )
        proc_ok = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/diff_check.py"),
                "--diff", str(diff_file), "--repo-root", str(self.root), "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_ok.returncode, 0)
        self.assertTrue(json.loads(proc_ok.stdout)["ok"])

        proc_bad = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/diff_check.py"),
                "--diff", str(diff_file), "--repo-root", str(self.root),
                "--pr-body", "Sure, here is the PR!", "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_bad.returncode, 1)
        payload = json.loads(proc_bad.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("DIFF-CHATBOT-OPENER", _codes(payload["errors"]))

    def test_test_skip_blocked_even_with_allow_test_edit_unless_allow_test_skip(self) -> None:
        py_skips = [
            "@unittest.skip('flaky')\ndef test_a():\n    assert True\n",
            "@unittest.skipIf(True, 'ci')\ndef test_b():\n    assert True\n",
            "@unittest.skipUnless(False, 'os')\ndef test_c():\n    assert True\n",
            "@pytest.mark.skip(reason='later')\ndef test_d():\n    assert True\n",
            "@pytest.mark.skipif(True, reason='slow')\ndef test_e():\n    assert True\n",
            "@pytest.mark.xfail(reason='broken')\ndef test_f():\n    assert False\n",
            "class T:\n    def test_g(self):\n        self.skipTest('later')\n",
            "def test_h():\n    pytest.skip('later')\n",
        ]
        for snippet in py_skips:
            diff = (
                "diff --git a/tests/test_worker.py b/tests/test_worker.py\n"
                "--- /dev/null\n"
                "+++ b/tests/test_worker.py\n"
                f"@@ -0,0 +1,{len(snippet.splitlines())} @@\n"
                + "".join(f"+{line}\n" for line in snippet.splitlines())
            )
            with self.subTest(snippet=snippet.splitlines()[0]):
                res = diff_check.check_diff(diff, allow_test_edit=True)
                self.assertFalse(res["ok"])
                self.assertIn("DIFF-TEST-SKIP", _codes(res["errors"]))
                self.assertNotIn("DIFF-UNAUTHORIZED-TEST-EDIT", _codes(res["errors"]))

                # Opt-in --allow-test-skip explicitly overrides DIFF-TEST-SKIP.
                overridden = diff_check.check_diff(
                    diff, allow_test_edit=True, allow_test_skip=True
                )
                self.assertTrue(overridden["ok"], msg=overridden["errors"])

        # AST verification on disk file: comments, docstrings, and strings mentioning skips pass,
        # while a real @pytest.mark.skip is blocked.
        disk_test = self.root / "tests" / "test_ast_skips.py"
        disk_test.write_text(
            '"""Never add @unittest.skip or pytest.skip() to mask failures."""\n'
            "import pytest\n\n"
            "def test_mentions_skip_in_strings_and_comments():\n"
            "    # @pytest.mark.skipif should not trigger inside a comment\n"
            '    blocked_tokens = ("@unittest.skip", "self.skipTest(", "pytest.skip(")\n'
            "    assert len(blocked_tokens) == 3\n",
            encoding="utf-8",
        )
        clean_ast = diff_check.check_files(
            ["tests/test_ast_skips.py"], repo_root=self.root, allow_test_edit=True
        )
        self.assertTrue(clean_ast["ok"], msg=clean_ast["errors"])

        # JS/TS test skips blocked even with allow_test_edit=True; comments/strings pass.
        for js_line in (
            "it.skip('retries on timeout', () => {});",
            "test.skip('parses payload', () => {});",
            "describe.skip('worker', () => {});",
            "xit('old case', () => {});",
            "xtest('disabled case', () => {});",
        ):
            js_diff = (
                "diff --git a/src/worker.test.ts b/src/worker.test.ts\n"
                "--- /dev/null\n"
                "+++ b/src/worker.test.ts\n"
                "@@ -0,0 +1,1 @@\n"
                f"+{js_line}\n"
            )
            with self.subTest(js_line=js_line):
                res_js = diff_check.check_diff(js_diff, allow_test_edit=True)
                self.assertFalse(res_js["ok"])
                self.assertIn("DIFF-TEST-SKIP", _codes(res_js["errors"]))

        js_clean_diff = (
            "diff --git a/src/worker.test.ts b/src/worker.test.ts\n"
            "--- /dev/null\n"
            "+++ b/src/worker.test.ts\n"
            "@@ -0,0 +1,4 @@\n"
            "+// Do not use it.skip() or xtest() here\n"
            "+test('checks forbidden token', () => {\n"
            "+  const forbidden = 'describe.skip(';\n"
            "+  expect(forbidden).toContain('skip');\n"
            "+});\n"
        )
        self.assertTrue(diff_check.check_diff(js_clean_diff, allow_test_edit=True)["ok"])

        # Deleting a pre-existing skip does not trigger DIFF-TEST-SKIP.
        removed_skip_diff = (
            "diff --git a/tests/test_app.py b/tests/test_app.py\n"
            "--- a/tests/test_app.py\n"
            "+++ b/tests/test_app.py\n"
            "@@ -1,3 +1,2 @@\n"
            "-@pytest.mark.skip('old')\n"
            " def test_ok():\n"
            "     assert True\n"
        )
        self.assertTrue(diff_check.check_diff(removed_skip_diff, allow_test_edit=True)["ok"])

    def test_unjustified_suppressions_flagged_and_valid_scoped_suppressions_pass(self) -> None:
        bad_cases = [
            ("src/a.py", "x = foo()  # type: ignore"),
            ("src/a.py", "x = foo()  # type: ignore  # missing code"),
            ("src/a.py", "x = foo()  # type: ignore[arg-type]"),
            ("src/a.py", "import os  # noqa"),
            ("src/a.py", "import os  # noqa: ALL"),
            ("src/b.ts", "// @ts-ignore\nconst x: number = 'a';"),
            ("src/b.ts", "// @ts-ignore legacy shim\nconst x: number = 'a';"),
            ("src/b.ts", "// @ts-expect-error\nconst x: number = 'a';"),
            ("src/b.ts", "/* eslint-disable */\nconsole.log(1);"),
            ("src/b.ts", "// eslint-disable-next-line\nconsole.log(1);"),
            ("src/b.ts", "// eslint-disable-next-line no-console\nconsole.log(1);"),
            ("src/b.ts", "// eslint-disable-next-line -- missing rule\nconsole.log(1);"),
            ("src/c.go", "func f() {} // nolint"),
            ("src/c.go", "func f() {} //nolint:errcheck"),
            ("src/c.go", "func f() {} // nolint:all // blanket"),
        ]
        for path, snippet in bad_cases:
            diff = (
                f"diff --git a/{path} b/{path}\n"
                "--- /dev/null\n"
                f"+++ b/{path}\n"
                f"@@ -0,0 +1,{len(snippet.splitlines())} @@\n"
                + "".join(f"+{line}\n" for line in snippet.splitlines())
            )
            with self.subTest(path=path, snippet=snippet):
                res = diff_check.check_diff(diff)
                self.assertFalse(res["ok"], msg=f"Expected DIFF-SUPPRESSION for {snippet!r}")
                self.assertIn("DIFF-SUPPRESSION", _codes(res["errors"]))

        # Valid neighbouring cases MUST PASS (both hunk mode and disk AST/tokenize mode).
        good_cases = [
            ("src/a.py", "import sys  # noqa: E402"),
            ("src/a.py", "x = foo()  # type: ignore[arg-type]  # upstream stub"),
            ("src/a.py", 'msg = "# type: ignore and # noqa inside string literal"'),
            ("src/a.py", "# Avoid bare # type: ignore or # noqa comments in new code"),
            ("src/b.ts", "// @ts-expect-error -- legacy CJS interop\nconst x = require('legacy');"),
            ("src/b.ts", "// eslint-disable-next-line no-console -- CLI output\nconsole.log('ok');"),
            ("src/b.ts", 'const note = "// @ts-ignore inside string";'),
            ("src/c.go", "func f() { _ = closeFn() } // nolint:errcheck // best-effort cleanup"),
        ]
        for path, snippet in good_cases:
            diff = (
                f"diff --git a/{path} b/{path}\n"
                "--- /dev/null\n"
                f"+++ b/{path}\n"
                f"@@ -0,0 +1,{len(snippet.splitlines())} @@\n"
                + "".join(f"+{line}\n" for line in snippet.splitlines())
            )
            with self.subTest(valid=snippet):
                res = diff_check.check_diff(diff)
                self.assertTrue(res["ok"], msg=res["errors"])

        # Disk Python tokenize verification.
        disk_py = self.root / "src" / "suppressions_ok.py"
        disk_py.write_text(
            "import sys  # noqa: E402\n"
            "val: int = 1  # type: ignore[arg-type]  # upstream stub\n"
            'EXAMPLE = "# type: ignore # noqa"\n',
            encoding="utf-8",
        )
        res_disk = diff_check.check_files(["src/suppressions_ok.py"], repo_root=self.root)
        self.assertTrue(res_disk["ok"], msg=res_disk["errors"])

    def test_silent_catch_flagged_while_narrowed_and_logged_handlers_pass(self) -> None:
        bad_py_snippets = [
            "def f():\n    try:\n        work()\n    except:\n        pass\n",
            "def f():\n    try:\n        work()\n    except Exception:\n        pass\n",
            "def f():\n    try:\n        work()\n    except BaseException:\n        ...\n",
            "def f():\n    try:\n        work()\n    except Exception:\n        return None\n",
            "def f():\n    try:\n        work()\n    except Exception:\n        return []\n",
            "def f():\n    try:\n        work()\n    except Exception:\n        return {}\n",
            "def f():\n    try:\n        work()\n    except Exception:\n        return False\n",
        ]
        for idx, snippet in enumerate(bad_py_snippets):
            diff = (
                "diff --git a/src/catch.py b/src/catch.py\n"
                "--- /dev/null\n"
                "+++ b/src/catch.py\n"
                f"@@ -0,0 +1,{len(snippet.splitlines())} @@\n"
                + "".join(f"+{line}\n" for line in snippet.splitlines())
            )
            with self.subTest(mode="hunk", idx=idx):
                res = diff_check.check_diff(diff)
                self.assertFalse(res["ok"])
                self.assertIn("DIFF-SILENT-CATCH", _codes(res["errors"]))
                self.assertNotIn("DIFF-STUB-PASS", _codes(res["errors"]))

            disk_path = self.root / "src" / f"bad_catch_{idx}.py"
            disk_path.write_text(snippet, encoding="utf-8")
            with self.subTest(mode="ast", idx=idx):
                res_ast = diff_check.check_files([f"src/bad_catch_{idx}.py"], repo_root=self.root)
                self.assertFalse(res_ast["ok"])
                self.assertIn("DIFF-SILENT-CATCH", _codes(res_ast["errors"]))

        # JS/TS empty catch (single-line and multi-line).
        for js_snippet in (
            "try { run(); } catch (err) {}",
            "try {\n  run();\n} catch (err) {\n  // ignore\n}",
        ):
            js_diff = (
                "diff --git a/src/catch.ts b/src/catch.ts\n"
                "--- /dev/null\n"
                "+++ b/src/catch.ts\n"
                f"@@ -0,0 +1,{len(js_snippet.splitlines())} @@\n"
                + "".join(f"+{line}\n" for line in js_snippet.splitlines())
            )
            with self.subTest(js_snippet=js_snippet):
                res_js = diff_check.check_diff(js_diff)
                self.assertFalse(res_js["ok"])
                self.assertIn("DIFF-SILENT-CATCH", _codes(res_js["errors"]))

        # Valid neighbouring cases MUST PASS (both hunk mode and AST mode):
        valid_py = (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n\n"
            "def cleanup(pid: int) -> None:\n"
            "    try:\n"
            "        kill(pid)\n"
            "    except ProcessLookupError:\n"
            "        pass\n\n"
            "def cleanup_group(pgid: int) -> None:\n"
            "    try:\n"
            "        killpg(pgid)\n"
            "    except (ProcessLookupError, PermissionError, OSError):\n"
            "        pass\n\n"
            "def fetch_with_log() -> None:\n"
            "    try:\n"
            "        work()\n"
            "    except Exception as exc:\n"
            "        logger.error('failed: %s', exc)\n"
            "        return None\n\n"
            "def fetch_reraise() -> None:\n"
            "    try:\n"
            "        work()\n"
            "    except Exception:\n"
            "        raise\n"
        )
        valid_diff = (
            "diff --git a/src/safe_catch.py b/src/safe_catch.py\n"
            "--- /dev/null\n"
            "+++ b/src/safe_catch.py\n"
            f"@@ -0,0 +1,{len(valid_py.splitlines())} @@\n"
            + "".join(f"+{line}\n" for line in valid_py.splitlines())
        )
        res_valid_hunk = diff_check.check_diff(valid_diff)
        self.assertTrue(res_valid_hunk["ok"], msg=res_valid_hunk["errors"])

        (self.root / "src" / "safe_catch.py").write_text(valid_py, encoding="utf-8")
        res_valid_ast = diff_check.check_files(["src/safe_catch.py"], repo_root=self.root)
        self.assertTrue(res_valid_ast["ok"], msg=res_valid_ast["errors"])

        valid_js_diff = (
            "diff --git a/src/safe.ts b/src/safe.ts\n"
            "--- /dev/null\n"
            "+++ b/src/safe.ts\n"
            "@@ -0,0 +1,4 @@\n"
            "+try {\n"
            "+  run();\n"
            "+} catch (err) {\n"
            "+  console.error(err);\n"
            "+}\n"
        )
        self.assertTrue(diff_check.check_diff(valid_js_diff)["ok"])

        # Weakening an existing broad except from `raise` to `pass` is caught.
        weakened_diff = (
            "diff --git a/src/existing.py b/src/existing.py\n"
            "--- a/src/existing.py\n"
            "+++ b/src/existing.py\n"
            "@@ -1,5 +1,5 @@\n"
            " try:\n"
            "     work()\n"
            " except Exception:\n"
            "-    raise\n"
            "+    pass\n"
        )
        res_weak = diff_check.check_diff(weakened_diff)
        self.assertFalse(res_weak["ok"])
        self.assertIn("DIFF-SILENT-CATCH", _codes(res_weak["errors"]))

    def test_debug_leftovers_flagged_outside_strings_and_comments(self) -> None:
        bad_cases = [
            ("src/dbg.py", "def run():\n    breakpoint()\n"),
            ("src/dbg.py", "import pdb\ndef run():\n    pdb.set_trace()\n"),
            ("src/dbg.py", "import ipdb\ndef run():\n    ipdb.set_trace()\n"),
            ("src/dbg.ts", "export function run() {\n  debugger;\n}\n"),
        ]
        for path, snippet in bad_cases:
            diff = (
                f"diff --git a/{path} b/{path}\n"
                "--- /dev/null\n"
                f"+++ b/{path}\n"
                f"@@ -0,0 +1,{len(snippet.splitlines())} @@\n"
                + "".join(f"+{line}\n" for line in snippet.splitlines())
            )
            with self.subTest(path=path, snippet=snippet):
                res = diff_check.check_diff(diff)
                self.assertFalse(res["ok"])
                self.assertIn("DIFF-DEBUG-LEFTOVER", _codes(res["errors"]))

        # Valid neighbouring cases: strings, comments, docstrings, and property access pass.
        clean_py = (
            '"""Never ship breakpoint() or pdb.set_trace() in production."""\n'
            "def check_text(s: str) -> bool:\n"
            "    # Reject ipdb.set_trace() in diffs\n"
            '    return "breakpoint()" not in s and "pdb.set_trace()" not in s\n'
        )
        (self.root / "src" / "clean_dbg.py").write_text(clean_py, encoding="utf-8")
        self.assertTrue(
            diff_check.check_files(["src/clean_dbg.py"], repo_root=self.root)["ok"]
        )
        clean_py_diff = (
            "diff --git a/src/clean_dbg_hunk.py b/src/clean_dbg_hunk.py\n"
            "--- /dev/null\n"
            "+++ b/src/clean_dbg_hunk.py\n"
            f"@@ -0,0 +1,{len(clean_py.splitlines())} @@\n"
            + "".join(f"+{line}\n" for line in clean_py.splitlines())
        )
        self.assertTrue(diff_check.check_diff(clean_py_diff)["ok"])

        clean_js_diff = (
            "diff --git a/src/clean_dbg.ts b/src/clean_dbg.ts\n"
            "--- /dev/null\n"
            "+++ b/src/clean_dbg.ts\n"
            "@@ -0,0 +1,4 @@\n"
            "+// Never leave debugger; in PRs\n"
            "+const label = 'debugger;';\n"
            "+const cfg = { debugger: false };\n"
            "+cfg.debugger = false;\n"
        )
        self.assertTrue(diff_check.check_diff(clean_js_diff)["ok"])

    def test_host_paths_flagged_while_explicit_placeholders_pass(self) -> None:
        bad_paths = [
            ("src/worker.py", 'KEY_PATH = "/Users/dev/keys/staging.pem"'),
            ("src/worker.py", 'DATA = "/home/ubuntu/work/data.json"'),
            ("src/worker.py", r'CERT = "C:\Users\alice\certs\prod.pem"'),
            ("src/worker.py", 'CERT = "C:\\\\Users\\\\bob\\\\certs\\\\prod.pem"'),
            ("docs/notes.md", "Loaded key from `/Users/dev/keys/staging.pem`."),
        ]
        for path, line in bad_paths:
            diff = (
                f"diff --git a/{path} b/{path}\n"
                "--- /dev/null\n"
                f"+++ b/{path}\n"
                "@@ -0,0 +1,1 @@\n"
                f"+{line}\n"
            )
            with self.subTest(path=path, line=line):
                res = diff_check.check_diff(diff)
                self.assertFalse(res["ok"])
                self.assertIn("DIFF-HOST-PATH", _codes(res["errors"]))

        # Valid neighbouring cases: explicit placeholders and web URLs pass cleanly.
        valid_md = (
            "# Paths\n\n"
            "Sanitized traces scrub `/Users/...`, `/Users/<user>/repo`, `/home/<user>/app`, "
            "`C:\\Users\\<user>\\repo`, `/Users/example/project`, `<HOME>/keys`, and `<REPO_ROOT>/src`.\n"
            "Web route `/home/about` and URL `https://example.com/home/alice/profile` stay allowed.\n"
        )
        self.assertEqual(diff_check.check_host_paths(valid_md, source="docs/paths.md"), [])

    def test_chatbot_closers_decorative_emojis_and_credibility_helpers(self) -> None:
        closers = [
            "Fixed retry backoff.\n\nLet me know if you'd like me to add benchmarks.",
            "Fixed retry backoff.\n\nLet me know if you\u2019d like me to add benchmarks.",
            "Fixed retry backoff.\n\nLet me know if you need anything else.",
            "Updated the parser. I hope this helps!",
            "Updated the parser.\n\nHope this helps.",
            "Blocked until tests pass.\n\nFeel free to reach out with questions.",
            "Ready for review. Happy to adjust if you want a smaller patch.",
            "Ready for review. Happy to help if anything breaks.",
        ]
        for body in closers:
            with self.subTest(body=body):
                res = diff_check.check_credibility_text(body, source="PR.md")
                self.assertFalse(res["ok"])
                self.assertIn("DIFF-CHATBOT-CLOSER", _codes(res["errors"]))

        # Valid neighbouring cases for closers: clean technical ending, fenced block, inline code.
        clean_doc = (
            "# Retry Worker Fix\n\n"
            "```text\n"
            "Hope this helps! Let me know if you'd like more changes.\n"
            "```\n\n"
            "The closer gate blocks phrases like `Hope this helps` and `Feel free to reach out`.\n"
            "Run `python3 -B scripts/check.py` before merging.\n"
        )
        clean_res = diff_check.check_credibility_text(clean_doc, source="PR.md")
        self.assertTrue(clean_res["ok"], msg=clean_res["errors"])
        self.assertEqual(clean_res["warnings"], [])

        # Decorative emojis: warning by default (ok=True), error only with strict_prose=True.
        for emoji in ("\U0001f680", "\u2728", "\U0001f525", "\U0001f389", "\U0001f4a1", "\U0001f3af", "\U0001f31f", "\U0001f4aa"):
            doc = f"## {emoji} Release Summary\n\nUpdated retry logic.\n"
            with self.subTest(emoji=emoji):
                warn_res = diff_check.check_credibility_text(doc, source="PR.md")
                self.assertTrue(warn_res["ok"], msg=warn_res["errors"])
                self.assertEqual(warn_res["errors"], [])
                self.assertIn("DIFF-DECORATIVE-EMOJI", _codes(warn_res["warnings"]))

                strict_res = diff_check.check_credibility_text(doc, source="PR.md", strict_prose=True)
                self.assertFalse(strict_res["ok"])
                self.assertIn("DIFF-DECORATIVE-EMOJI", _codes(strict_res["errors"]))

        # Decorative emojis inside fenced code blocks or inline backticks are ignored.
        fenced_emoji_doc = (
            "# Emoji Fixture\n\n"
            "Inline code `\U0001f680` is ignored.\n\n"
            "```text\n"
            "\u2728 Ship it! \U0001f525\n"
            "```\n"
        )
        fenced_res = diff_check.check_credibility_text(fenced_emoji_doc, source="PR.md", strict_prose=True)
        self.assertTrue(fenced_res["ok"], msg=fenced_res["errors"])
        self.assertEqual(fenced_res["warnings"], [])

        # Reusable check_diff_and_text combines diff checks and PR text checks cleanly.
        combo_diff = (
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -1,2 +1,3 @@\n"
            " def add(a: int, b: int) -> int:\n"
            "+    breakpoint()\n"
            "     return a + b\n"
        )
        combo = diff_check.check_diff_and_text(
            combo_diff,
            text="## \U0001f680 Summary\n\nAdded debug hook.\n\nHope this helps!",
            text_source="PR.md",
        )
        self.assertFalse(combo["ok"])
        self.assertIn("DIFF-DEBUG-LEFTOVER", _codes(combo["errors"]))
        self.assertIn("DIFF-CHATBOT-CLOSER", _codes(combo["errors"]))
        self.assertIn("DIFF-DECORATIVE-EMOJI", _codes(combo["warnings"]))

    def test_diff_check_cli_allow_test_skip_and_strict_prose_flags(self) -> None:
        skip_diff = self.root / "skip.diff"
        skip_diff.write_text(
            "diff --git a/tests/test_app.py b/tests/test_app.py\n"
            "--- a/tests/test_app.py\n"
            "+++ b/tests/test_app.py\n"
            "@@ -1,2 +1,3 @@\n"
            "+@pytest.mark.skip(reason='later')\n"
            " def test_ok():\n"
            "     assert True\n",
            encoding="utf-8",
        )
        proc_blocked = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/diff_check.py"),
                "--diff", str(skip_diff), "--repo-root", str(self.root),
                "--allow-test-edit", "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_blocked.returncode, 1)
        self.assertIn("DIFF-TEST-SKIP", _codes(json.loads(proc_blocked.stdout)["errors"]))

        proc_allowed = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/diff_check.py"),
                "--diff", str(skip_diff), "--repo-root", str(self.root),
                "--allow-test-edit", "--allow-test-skip", "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_allowed.returncode, 0)
        self.assertTrue(json.loads(proc_allowed.stdout)["ok"])

        # --strict-prose promotes decorative emoji warning to exit 1.
        proc_warn = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/diff_check.py"),
                "--repo-root", str(self.root),
                "--pr-body", "## \U0001f680 Shipped\n\nUpdated parser.",
                "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_warn.returncode, 0)
        warn_payload = json.loads(proc_warn.stdout)
        self.assertTrue(warn_payload["ok"])
        self.assertIn("DIFF-DECORATIVE-EMOJI", _codes(warn_payload["warnings"]))

        proc_strict = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/diff_check.py"),
                "--repo-root", str(self.root),
                "--pr-body", "## \U0001f680 Shipped\n\nUpdated parser.",
                "--strict-prose", "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_strict.returncode, 1)
        strict_payload = json.loads(proc_strict.stdout)
        self.assertFalse(strict_payload["ok"])
        self.assertIn("DIFF-DECORATIVE-EMOJI", _codes(strict_payload["errors"]))


class GateAssetsIntegrityTests(unittest.TestCase):
    def test_model_deltas_json_covers_all_five_models_with_stable_ids(self) -> None:
        data = json.loads((REPO_ROOT / "gates/model_deltas.json").read_text(encoding="utf-8"))
        expected_prefixes = {
            "gpt-6.2-astra": "D-AST",
            "gpt-6.2-sol": "D-SOL",
            "claude-opus-5-5": "D-OPU",
            "claude-fable-5-2": "D-FAB",
            "gemini-4-neon": "D-NEO",
        }
        self.assertEqual(set(data["models"].keys()), set(expected_prefixes.keys()))
        seen_ids = set()
        for model_id, prefix in expected_prefixes.items():
            entry = data["models"][model_id]
            self.assertEqual(entry["model_id"], model_id)
            self.assertEqual(entry["delta_prefix"], prefix)
            self.assertIn("default_effort_routing", entry)
            self.assertGreaterEqual(len(entry["rules"]), 2)
            for rule in entry["rules"]:
                rid = rule["id"]
                self.assertTrue(rid.startswith(prefix + "-"), msg=rid)
                self.assertNotIn(rid, seen_ids)
                seen_ids.add(rid)
                for field in ("target_failure_mode", "rule", "falsification_check", "valid_neighbouring_case"):
                    self.assertTrue(isinstance(rule[field], str) and rule[field].strip(), msg=(rid, field))
                # Ensure GPT-6.2 deltas themselves never include banned legacy concision phrasing.
                if model_id.startswith("gpt-6.2-"):
                    self.assertIsNone(api_checks.GPT_BANNED_CONCISE_RE.search(rule["rule"]))
        opus_ids = {r["id"] for r in data["models"]["claude-opus-5-5"]["rules"]}
        self.assertIn("D-OPU-4", opus_ids)
        opu4 = next(r for r in data["models"]["claude-opus-5-5"]["rules"] if r["id"] == "D-OPU-4")
        self.assertIn("LOCAL-01", opu4.get("evidence_refs", []))

    def test_vale_rules_levels_and_technical_allowlist_valid_neighbouring_case(self) -> None:
        style_dir = REPO_ROOT / "gates/vale/styles/AntiSlop"
        openers = _parse_simple_vale_yaml(style_dir / "Openers.yml")
        closers = _parse_simple_vale_yaml(style_dir / "Closers.yml")
        adr = _parse_simple_vale_yaml(style_dir / "ADRStructure.yml")
        vocab = _parse_simple_vale_yaml(style_dir / "Vocab.yml")
        phrasing = _parse_simple_vale_yaml(style_dir / "Phrasing.yml")

        self.assertEqual(openers["level"], "error")
        self.assertEqual(closers["level"], "error")
        self.assertEqual(adr["level"], "warning")
        self.assertEqual(vocab["level"], "warning")
        self.assertEqual(phrasing["level"], "warning")

        for closer_phrase in (
            "Let me know if you'd like me to add tests.",
            "Let me know if you need anything else.",
            "I hope this helps!",
            "Hope this helps.",
            "Feel free to reach out if anything breaks.",
            "Happy to adjust if needed.",
            "Happy to help if you hit issues.",
        ):
            self.assertTrue(
                any(re.search(t, closer_phrase, re.IGNORECASE) for t in closers["tokens"]),
                msg=f"Closers.yml did not match {closer_phrase!r}",
            )
        clean_closing = "Run python3 -B scripts/check.py before merging."
        for token in closers["tokens"]:
            self.assertIsNone(
                re.search(token, clean_closing, re.IGNORECASE),
                msg=f"Closers.yml token {token!r} falsely matched clean closing",
            )

        required_allowlist = {"vector", "harness", "primitive", "surface", "substrate", "features"}
        self.assertTrue(required_allowlist.issubset(set(vocab["exceptions"])))
        self.assertTrue(required_allowlist.issubset(set(phrasing["exceptions"])))

        # Valid neighbouring case: technical doc using all 6 allowlisted terms triggers 0 Vocab/Phrasing hits.
        technical_doc = (
            "The evaluation harness stores each embedding vector and extracts model features "
            "from the API surface. The storage substrate exposes a lock-free primitive."
        )
        for token in vocab["tokens"]:
            self.assertIsNone(
                re.search(rf"\b(?:{token})\b", technical_doc, re.IGNORECASE),
                msg=f"Vocab token {token!r} falsely matched technical doc",
            )
        for token in phrasing["tokens"]:
            self.assertIsNone(
                re.search(token, technical_doc, re.IGNORECASE),
                msg=f"Phrasing token {token!r} falsely matched technical doc",
            )

        # Positive cases: clichés and contrast filler ARE caught by Vocab / Phrasing tokens.
        slop_doc = "We delve into a robust tapestry that is not just fast, but also serves as a testament."
        self.assertTrue(any(re.search(rf"\b(?:{t})\b", slop_doc, re.IGNORECASE) for t in vocab["tokens"]))
        self.assertTrue(any(re.search(t, slop_doc, re.IGNORECASE) for t in phrasing["tokens"]))

        # ADRStructure regex matches a complete 4-field ADR and fails an incomplete one.
        complete_adr = (
            "## Decision\nUse stdlib Python.\n"
            "## Rejected Alternatives\nExternal daemon.\n"
            "## Failure Mode\nConfig drift.\n"
            "## Falsification Condition\nAny false positive on valid neighbouring cases.\n"
        )
        incomplete_adr = "## Decision\nUse stdlib Python.\n"
        self.assertGreaterEqual(len(re.findall(adr["token"], complete_adr, re.IGNORECASE)), 4)
        self.assertLess(len(re.findall(adr["token"], incomplete_adr, re.IGNORECASE)), 4)

    def test_ci_ratchet_workflow_and_gates_readme_self_check(self) -> None:
        ci_text = (REPO_ROOT / "gates/ci-ratchet.yml").read_text(encoding="utf-8")
        for job in ("diff-gate:", "api-config-gate:", "code-hygiene-ratchet:", "prose-vale-ratchet:"):
            self.assertIn(job, ci_text)
        # Keep warning-first Vale alerts visible in CI instead of suppressing warnings.
        self.assertNotIn("--minAlertLevel=error", ci_text)

        # Dogfood diff_check on gates/README.md, gates/api_checks.py, and gates/diff_check.py:
        # zero chatbot openers, zero broken repo paths, and zero false-positive stubs on strings/docstrings.
        dogfood_res = diff_check.check_files(
            ["gates/README.md", "gates/api_checks.py", "gates/diff_check.py"],
            repo_root=REPO_ROOT,
        )
        self.assertTrue(dogfood_res["ok"], msg=dogfood_res["errors"])

        # Dogfood diff_check across repo Markdown docs (excluding ignored dirs, raw model outputs, per-run review logs, and fictional benchmark source packets).
        excluded_parts = {".git", ".venv", "runs-local", "artifacts", "reviews"}
        all_md = sorted(
            str(p.relative_to(REPO_ROOT)).replace("\\", "/")
            for p in REPO_ROOT.rglob("*.md")
            if not (excluded_parts & set(p.parts))
            and p.relative_to(REPO_ROOT).parts[:2] != ("benchmarks", "sources")
        )
        self.assertGreaterEqual(len(all_md), 15)
        all_md_res = diff_check.check_files(all_md, repo_root=REPO_ROOT, max_files=0)
        self.assertTrue(all_md_res["ok"], msg=all_md_res["errors"])

    def test_diff_check_exclude_globs_in_diff_and_files_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "results/pilot-v0.7.0/artifacts/run1").mkdir(parents=True)
            (root / "results/a/b/artifacts").mkdir(parents=True)
            (root / "benchmarks/sources/pkg").mkdir(parents=True)
            (root / "src/nested/sub").mkdir(parents=True)

            # Excluded files containing broken repo paths and debug leftovers.
            artifact_md = root / "results/pilot-v0.7.0/artifacts/run1/stage-1.md"
            artifact_md.write_text("Isolated workspace edited `tests/test_promos.py`.\n", encoding="utf-8")
            source_py = root / "benchmarks/sources/pkg/fixture.py"
            source_py.write_text("def run():\n    breakpoint()\n", encoding="utf-8")

            # Non-excluded files:
            # 1) results/pilot-v0.7.0/README.md (not under artifacts/)
            # 2) results/a/b/artifacts/note.md (single '*' must not cross '/')
            # 3) src/app.py (real production code)
            readme_md = root / "results/pilot-v0.7.0/README.md"
            readme_md.write_text("Broken doc link `src/does_not_exist.py`.\n", encoding="utf-8")
            deep_md = root / "results/a/b/artifacts/note.md"
            deep_md.write_text("Broken doc link `src/also_missing.py`.\n", encoding="utf-8")
            app_py = root / "src/app.py"
            app_py.write_text("def run():\n    breakpoint()\n", encoding="utf-8")
            nested_py = root / "src/nested/sub/gen.py"
            nested_py.write_text("def run():\n    breakpoint()\n", encoding="utf-8")

            excludes = ["results/*/artifacts/**", "benchmarks/sources/**", "src/**/gen.py"]

            # 1. check_files skips matched paths (including '**' matching nested dirs).
            excluded_only_res = diff_check.check_files(
                [
                    "results/pilot-v0.7.0/artifacts/run1/stage-1.md",
                    "benchmarks/sources/pkg/fixture.py",
                    "src/nested/sub/gen.py",
                ],
                repo_root=root,
                exclude=excludes,
            )
            self.assertTrue(excluded_only_res["ok"], msg=excluded_only_res["errors"])
            self.assertEqual(excluded_only_res["stats"]["files_changed"], 0)

            # Non-excluded paths still fail cleanly in check_files.
            mixed_files_res = diff_check.check_files(
                [
                    "results/pilot-v0.7.0/artifacts/run1/stage-1.md",
                    "benchmarks/sources/pkg/fixture.py",
                    "results/pilot-v0.7.0/README.md",
                    "results/a/b/artifacts/note.md",
                    "src/app.py",
                ],
                repo_root=root,
                exclude=excludes,
            )
            self.assertFalse(mixed_files_res["ok"])
            flagged_files = {e.get("file") for e in mixed_files_res["errors"]}
            self.assertNotIn("results/pilot-v0.7.0/artifacts/run1/stage-1.md", flagged_files)
            self.assertNotIn("benchmarks/sources/pkg/fixture.py", flagged_files)
            self.assertEqual(
                flagged_files,
                {"results/pilot-v0.7.0/README.md", "results/a/b/artifacts/note.md", "src/app.py"},
            )

            # 2. check_diff skips excluded sections (and excludes them from stats/budgets),
            # while still flagging non-excluded files and preserving structural checks on them.
            excluded_diff = (
                "diff --git a/results/pilot-v0.7.0/artifacts/run1/stage-1.md b/results/pilot-v0.7.0/artifacts/run1/stage-1.md\n"
                "new file mode 100644\n"
                "--- /dev/null\n"
                "+++ b/results/pilot-v0.7.0/artifacts/run1/stage-1.md\n"
                "@@ -0,0 +1,1 @@\n"
                "+Isolated workspace edited `tests/test_promos.py`.\n"
                "diff --git a/benchmarks/sources/pkg/fixture.py b/benchmarks/sources/pkg/fixture.py\n"
                "new file mode 100644\n"
                "--- /dev/null\n"
                "+++ b/benchmarks/sources/pkg/fixture.py\n"
                "@@ -0,0 +1,2 @@\n"
                "+def run():\n"
                "+    breakpoint()\n"
            )
            self.assertFalse(diff_check.check_diff(excluded_diff, repo_root=root)["ok"])
            diff_ok = diff_check.check_diff(excluded_diff, repo_root=root, exclude=excludes)
            self.assertTrue(diff_ok["ok"], msg=diff_ok["errors"])
            self.assertEqual(diff_ok["stats"]["files_changed"], 0)

            mixed_diff = (
                excluded_diff
                + "diff --git a/src/app.py b/src/app.py\n"
                "new file mode 100644\n"
                "--- /dev/null\n"
                "+++ b/src/app.py\n"
                "@@ -0,0 +1,2 @@\n"
                "+def run():\n"
                "+    breakpoint()\n"
            )
            diff_mixed = diff_check.check_diff(mixed_diff, repo_root=root, exclude=excludes)
            self.assertFalse(diff_mixed["ok"])
            self.assertEqual({e.get("file") for e in diff_mixed["errors"]}, {"src/app.py"})
            self.assertEqual({e["code"] for e in diff_mixed["errors"]}, {"DIFF-DEBUG-LEFTOVER"})
            self.assertEqual(diff_mixed["stats"]["files_changed"], 1)

            # 3. Repeatable CLI --exclude works end-to-end.
            diff_file = root / "mixed.diff"
            diff_file.write_text(excluded_diff, encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable, "-B", str(REPO_ROOT / "gates/diff_check.py"),
                    "--diff", str(diff_file),
                    "--repo-root", str(root),
                    "--exclude", "results/*/artifacts/**",
                    "--exclude", "benchmarks/sources/**",
                    "--json",
                ],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            self.assertTrue(json.loads(proc.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
