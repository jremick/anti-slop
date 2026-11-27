"""Stdlib-only tests for Pillar 1: AI-era structural slop detectors (gates/structural.py),
plain-English review workflow (gates/review.py), and diff_check.py --structural/--explain flags.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gates import diff_check  # noqa: E402
from gates import review  # noqa: E402
from gates import structural  # noqa: E402


def _codes(items) -> set[str]:
    return {item["code"] for item in items}


def _new_file_diff(rel_path: str, content: str) -> str:
    lines = content.splitlines()
    body = "".join(f"+{ln}\n" for ln in lines)
    return (
        f"diff --git a/{rel_path} b/{rel_path}\n"
        f"--- /dev/null\n"
        f"+++ b/{rel_path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}"
    )


class StructuralDetectorsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_test_theater_catches_bad_and_allows_valid_neighbours(self) -> None:
        bad_py = (
            "from unittest.mock import patch, MagicMock\n\n"
            "def test_no_assert():\n"
            "    x = 1 + 2\n"
            "    return x\n\n"
            "def test_tautology():\n"
            "    assert True\n\n"
            "def test_self_eq():\n"
            "    val = compute()\n"
            "    assert val == val\n\n"
            "@patch('app.db')\n"
            "@patch('app.cache')\n"
            "@patch('app.http')\n"
            "def test_over_mocked(m1, m2, m3):\n"
            "    run_job()\n"
            "    m1.assert_called_once()\n"
        )
        hits = structural.check_test_theater_in_source("tests/test_bad.py", bad_py)
        kinds = {h["meta"]["kind"] for h in hits}
        self.assertEqual(kinds, {"assertion_free", "tautological", "over_mocked"})
        self.assertEqual(len(hits), 4)

        # Valid neighbouring cases: real assertions, pytest.raises, helper delegation,
        # and 2 mocks with a real output assertion (verifies decorators are not double-counted).
        good_py = (
            "import pytest\n"
            "from unittest.mock import patch\n\n"
            "def _helper(x):\n"
            "    return x * 2\n\n"
            "def test_real_value():\n"
            "    assert _helper(3) == 6\n\n"
            "def test_raises():\n"
            "    with pytest.raises(ValueError):\n"
            "        parse('bad')\n\n"
            "def test_helper_assert():\n"
            "    assert_valid_payload({'ok': True})\n\n"
            "@patch('app.clock')\n"
            "@patch('app.net')\n"
            "def test_two_mocks_real_assert(m1, m2):\n"
            "    m1.return_value = 10\n"
            "    res = run_sync()\n"
            "    assert res['status'] == 'ok'\n"
            "    m2.assert_called_once()\n\n"
            "@patch('app.a')\n"
            "@patch('app.b')\n"
            "def test_two_mocks_only_mock_assert_below_threshold(m1, m2):\n"
            "    run_sync()\n"
            "    m1.assert_called_once()\n"
        )
        clean_hits = structural.check_test_theater_in_source("tests/test_good.py", good_py)
        self.assertEqual(clean_hits, [], msg=clean_hits)

        # JS/TS test theater vs valid neighbour
        bad_ts = (
            "test('does nothing', () => {\n"
            "  computeTotal(5);\n"
            "});\n"
            "it('always passes', () => {\n"
            "  expect(true).toBe(true);\n"
            "});\n"
        )
        ts_hits = structural.check_test_theater_in_source("src/billing.test.ts", bad_ts)
        self.assertEqual(len(ts_hits), 2)

        good_ts = (
            "test('computes total', () => {\n"
            "  expect(computeTotal(5)).toBe(500);\n"
            "});\n"
        )
        self.assertEqual(
            structural.check_test_theater_in_source("src/billing.test.ts", good_ts), []
        )

    def test_silent_fallback_catches_bad_and_allows_valid_neighbours(self) -> None:
        bad_py = (
            "import os\n\n"
            "SECRET = os.environ.get('JWT_SECRET', 'hardcoded-dev-secret')\n\n"
            "def fetch_rate():\n"
            "    try:\n"
            "        return call_api()\n"
            "    except Exception:\n"
            "        return 0\n\n"
            "def parse_label():\n"
            "    try:\n"
            "        return read_label()\n"
            "    except:\n"
            "        label = 'unknown'\n"
            "        return label\n"
        )
        hits = structural.check_silent_fallbacks_in_source("src/rates.py", bad_py)
        self.assertEqual(len(hits), 3, msg=hits)
        kinds = {h["meta"]["kind"] for h in hits}
        self.assertEqual(kinds, {"sensitive_env_default", "broad_except_fallback"})

        # Valid neighbouring cases: narrowed exception, logged broad exception,
        # non-secret env default, and `except Exception: pass` (handled by DIFF-SILENT-CATCH).
        good_py = (
            "import logging\nimport os\n\n"
            "LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')\n"
            "TOKEN = os.environ.get('API_TOKEN')\n\n"
            "def fetch_narrow():\n"
            "    try:\n"
            "        return lookup()\n"
            "    except KeyError:\n"
            "        return 0\n\n"
            "def fetch_logged():\n"
            "    try:\n"
            "        return call_api()\n"
            "    except Exception as exc:\n"
            "        logging.warning('rate fetch failed: %s', exc)\n"
            "        return 0\n\n"
            "def handled_by_diff_silent_catch():\n"
            "    try:\n"
            "        return call_api()\n"
            "    except Exception:\n"
            "        pass\n"
        )
        self.assertEqual(
            structural.check_silent_fallbacks_in_source("src/rates.py", good_py), []
        )

        # JS/TS catch fallback vs logged catch
        bad_js = "function f() { try { return parse(); } catch (e) { return 0; } }\n"
        self.assertEqual(
            len(structural.check_silent_fallbacks_in_source("src/rates.ts", bad_js)), 1
        )
        good_js = "function f() { try { return parse(); } catch (e) { console.error(e); return 0; } }\n"
        self.assertEqual(
            structural.check_silent_fallbacks_in_source("src/rates.ts", good_js), []
        )

    def test_duplicate_block_catches_renamed_clones_and_allows_short_or_flat_code(self) -> None:
        existing_py = (
            "def price_order(items, tax_bps):\n"
            "    subtotal = 0\n"
            "    for item in items:\n"
            "        if item['qty'] <= 0:\n"
            "            raise ValueError('bad qty')\n"
            "        subtotal += item['unit_cents'] * item['qty']\n"
            "    tax = (subtotal * tax_bps + 5000) // 10000\n"
            "    total = subtotal + tax\n"
            "    return {'subtotal': subtotal, 'tax': tax, 'total': total}\n"
        )
        # Copy-pasted with renamed local variables into a second file!
        cloned_py = (
            "def price_upgrade(lines, rate_bps):\n"
            "    base = 0\n"
            "    for row in lines:\n"
            "        if row['qty'] <= 0:\n"
            "            raise ValueError('bad qty')\n"
            "        base += row['unit_cents'] * row['qty']\n"
            "    fee = (base * rate_bps + 5000) // 10000\n"
            "    grand = base + fee\n"
            "    return {'subtotal': base, 'tax': fee, 'total': grand}\n"
        )
        (self.root / "src").mkdir()
        (self.root / "src/pricing.py").write_text(existing_py, encoding="utf-8")
        (self.root / "src/upgrades.py").write_text(cloned_py, encoding="utf-8")

        diff_txt = _new_file_diff("src/upgrades.py", cloned_py)
        res = structural.check_structural_diff(diff_txt, repo_root=self.root)
        self.assertIn("STRUCT-DUPLICATE-BLOCK", _codes(res["warnings"]))

        # Valid neighbouring case: flat config assignments or short 3-line helpers do NOT collide.
        flat_a = (
            "def config_a():\n"
            "    a = 1\n    b = 2\n    c = 3\n    d = 4\n    e = 5\n    f = 6\n    return a\n"
        )
        flat_b = (
            "def config_b():\n"
            "    x = 10\n    y = 20\n    z = 30\n    u = 40\n    v = 50\n    w = 60\n    return x\n"
        )
        dup_flat = structural.check_duplicate_blocks({
            "src/a.py": (flat_a, None),
            "src/b.py": (flat_b, None),
        })
        self.assertEqual(dup_flat, [])

    def test_dead_compat_catches_unreachable_legacy_and_orphans_while_allowing_live_helpers(self) -> None:
        bad_py = (
            "def calculate_legacy(amount):\n"
            "    return amount * 2\n\n"
            "def _orphan_recursive(n):\n"
            "    return 1 if n <= 1 else _orphan_recursive(n - 1)\n\n"
            "def charge(amount, allow_legacy_mode=False):\n"
            "    if False:\n"
            "        return 0\n"
            "    return amount\n"
        )
        hits = structural.check_dead_compat_in_source("src/billing.py", bad_py)
        kinds = {h["meta"]["kind"] for h in hits}
        self.assertEqual(
            kinds,
            {"unreachable_branch", "dead_legacy_symbol", "orphaned_private_helper", "legacy_param"},
        )

        # Valid neighbouring case: live private helper, decorated helper, and legacy symbol called elsewhere.
        good_py = (
            "from typing import TYPE_CHECKING\n\n"
            "def _round_cents(v):\n"
            "    return int(v)\n\n"
            "def register(fn):\n"
            "    return fn\n\n"
            "@register\n"
            "def _decorated_handler():\n"
            "    return 1\n\n"
            "def legacy_adapter(x):\n"
            "    return _round_cents(x)\n"
        )
        clean = structural.check_dead_compat_in_source(
            "src/billing.py",
            good_py,
            extra_sources={"src/caller.py": "from billing import legacy_adapter\nlegacy_adapter(5)\n"},
        )
        self.assertEqual(clean, [], msg=clean)

    def test_god_growth_flags_growing_monolith_and_allows_shrinking_large_file(self) -> None:
        long_fn_lines = ["def giant(x):"] + [f"    if x == {i}:\n        return {i}" for i in range(15)] + ["    return -1"]
        long_fn = "\n".join(long_fn_lines) + "\n"
        hits = structural.check_god_growth_in_source("src/engine.py", long_fn)
        self.assertIn("STRUCT-GOD-FUNCTION", _codes(hits))

        big_file = "\n".join(f"CONST_{i} = {i}" for i in range(420)) + "\n"
        # Growing file (+10 net LOC) -> flagged as STRUCT-GOD-FILE.
        grow_hits = structural.check_god_growth_in_source(
            "src/monolith.py", big_file, net_loc_delta=10
        )
        self.assertIn("STRUCT-GOD-FILE", _codes(grow_hits))

        # Shrinking existing big file (-5 net LOC) -> must NOT be penalized!
        shrink_hits = structural.check_god_growth_in_source(
            "src/monolith.py", big_file, net_loc_delta=-5
        )
        self.assertNotIn("STRUCT-GOD-FILE", _codes(shrink_hits))

    def test_scope_sprawl_flags_4_prod_areas_and_allows_focused_feature_with_tests_and_docs(self) -> None:
        sprawl = structural.check_scope_sprawl([
            "src/billing/calc.py",
            "src/auth/tokens.py",
            "src/emails/send.py",
            "src/analytics/events.py",
        ])
        self.assertEqual(_codes(sprawl), {"STRUCT-SCOPE-SPRAWL"})

        focused = structural.check_scope_sprawl([
            "src/billing/calc.py",
            "src/billing/models.py",
            "src/billing/api.py",
            "tests/test_billing.py",
            "docs/billing.md",
            "README.md",
        ])
        self.assertEqual(focused, [])

    def test_commented_code_catches_bad_and_allows_valid_neighbours(self) -> None:
        # 1. Python commented-out code blocks (control flow, imports/assigns, multi-line call).
        bad_py = (
            "def active(x):\n"
            "    # def old_price(items, rate):\n"
            "    #     if rate < 0:\n"
            "    #         return 0\n"
            "    #     return sum(items) * rate\n"
            "    return x * 2\n\n"
            "# import legacy_sdk\n"
            "# client = legacy_sdk.connect()\n"
            "# client.flush_all()\n"
        )
        py_hits = structural.check_commented_code_in_source("src/billing.py", bad_py)
        self.assertEqual(len(py_hits), 2, msg=py_hits)
        self.assertEqual(_codes(py_hits), {"STRUCT-COMMENTED-CODE"})
        self.assertEqual(py_hits[0]["line"], 2)
        self.assertEqual(py_hits[0]["meta"]["end_line"], 5)

        # 2. JS/TS // and non-JSDoc /* */ commented-out code blocks.
        bad_ts = (
            "export function charge(x: number) {\n"
            "  // const fee = computeLegacyFee(x);\n"
            "  // if (fee > 0) {\n"
            "  //   return x + fee;\n"
            "  // }\n"
            "  /*\n"
            "   * const backup = x * 2;\n"
            "   * const fn = (v) => { return v + 1; };\n"
            "   * return fn(backup);\n"
            "   */\n"
            "  return x;\n"
            "}\n"
        )
        ts_hits = structural.check_commented_code_in_source("src/billing.ts", bad_ts)
        self.assertEqual(len(ts_hits), 2, msg=ts_hits)

        # 3. Go commented-out code block.
        bad_go = (
            "package billing\n"
            "// func oldCharge(x int) int {\n"
            "//     fee := x * 2\n"
            "//     if fee > 10 {\n"
            "//         return fee\n"
            "//     }\n"
            "//     return x\n"
            "// }\n"
            "func Charge(x int) int { return x }\n"
        )
        go_hits = structural.check_commented_code_in_source("billing.go", bad_go)
        self.assertEqual(len(go_hits), 1, msg=go_hits)

        # 4. Valid neighbouring cases: prose, 1-2 line invariant notes, license headers,
        # docstrings, JSDoc @example, fenced code inside comments, URLs, bullets, dividers, HTTP headers.
        good_py = (
            "# Copyright (c) 2026 Example Corp.\n"
            "# Licensed under the MIT License.\n"
            "# Permission is hereby granted, free of charge.\n"
            "# Without warranty of any kind.\n\n"
            '"""Module docstring example:\n'
            "def demo(x):\n"
            "    if x > 0:\n"
            "        return x + 1\n"
            '"""\n\n'
            "# ==========================================\n"
            "# Payment webhook processing invariants\n"
            "# ==========================================\n"
            "# INVARIANT: Stripe webhooks can arrive out of order.\n"
            "# Only update status when event.created_at >= sub.last_event_at.\n"
            "# See https://example.com/docs/webhooks for retries (optional)\n"
            "# if the server returns an error:\n"
            "# for example, retry with exponential backoff\n"
            "# return the cached response to the caller\n"
            "# - [x] validate signature header\n"
            "# - [ ] emit metrics counter\n"
            "# Content-Type: application/json\n"
            "# ```python\n"
            "# def fenced_example(x):\n"
            "#     y = x + 1\n"
            "#     return y\n"
            "# ```\n"
            "# Short 2-line code hint allowed (< 3 lines):\n"
            "# total = a + b\n"
            "# return total\n"
            "def live(x):\n"
            "    return x + 1  # old: return x\n"
        )
        self.assertEqual(
            structural.check_commented_code_in_source("src/webhooks.py", good_py),
            [],
        )

        good_ts = (
            "/**\n"
            " * Example usage:\n"
            " * @example\n"
            " * const app = new Hono();\n"
            " * app.get('/', (c) => c.text('ok'));\n"
            " * export default app;\n"
            " */\n"
            "// -----------------------------------------\n"
            "// If the response stream closes early, keep the last cursor.\n"
            "// See https://example.com/stream for details.\n"
            "// - step 1: check header\n"
            "// - step 2: return status\n"
            "// ```ts\n"
            "// const x = 1;\n"
            "// const y = 2;\n"
            "// return x + y;\n"
            "// ```\n"
            "export const ok = true;\n"
        )
        self.assertEqual(
            structural.check_commented_code_in_source("src/stream.ts", good_ts),
            [],
        )

        # 5. Diff-scoping: touching only 1 line of an existing commented block does not fire;
        # adding >= 3 new commented code lines fires as warning by default and error with --strict-structural.
        self.assertEqual(
            structural.check_commented_code_in_source("src/billing.py", bad_py, added_lines={2}),
            [],
        )
        diff_txt = _new_file_diff("src/billing.py", bad_py)
        warn_res = structural.check_structural_diff(diff_txt, repo_root=None, strict_structural=False)
        self.assertIn("STRUCT-COMMENTED-CODE", _codes(warn_res["warnings"]))
        self.assertEqual(warn_res["errors"], [])

        strict_res = structural.check_structural_diff(diff_txt, repo_root=None, strict_structural=True)
        self.assertIn("STRUCT-COMMENTED-CODE", _codes(strict_res["errors"]))


class PlainEnglishReviewAndCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_catalog_covers_all_core_and_structural_codes(self) -> None:
        expected_codes = {
            "DIFF-TEST-SKIP",
            "DIFF-UNAUTHORIZED-TEST-EDIT",
            "DIFF-SUPPRESSION",
            "DIFF-SILENT-CATCH",
            "DIFF-DEBUG-LEFTOVER",
            "DIFF-HOST-PATH",
            "DIFF-STUB-TODO",
            "DIFF-STUB-NOT-IMPLEMENTED",
            "DIFF-STUB-PASS",
            "DIFF-CHATBOT-OPENER",
            "DIFF-CHATBOT-CLOSER",
            "DIFF-BROKEN-DOC-PATH",
            "DIFF-DECORATIVE-EMOJI",
            "DIFF-MAX-NET-LOC",
            "DIFF-MAX-FILES",
            "STRUCT-TEST-THEATER",
            "STRUCT-SILENT-FALLBACK",
            "STRUCT-DUPLICATE-BLOCK",
            "STRUCT-DEAD-COMPAT",
            "STRUCT-COMMENTED-CODE",
            "STRUCT-GOD-FUNCTION",
            "STRUCT-GOD-FILE",
            "STRUCT-SCOPE-SPRAWL",
        }
        self.assertTrue(expected_codes.issubset(set(review.PLAIN_ENGLISH_CATALOG.keys())))
        for code in expected_codes:
            entry = review.PLAIN_ENGLISH_CATALOG[code]
            for field in ("title", "why_veterans_flag_it", "how_it_compounds", "fix_prompt", "evidence"):
                self.assertTrue(entry[field].strip(), msg=(code, field))

        # Verification Hierarchy guidance in STRUCT-TEST-THEATER and comment poisoning in STRUCT-COMMENTED-CODE.
        theater_exp = review.PLAIN_ENGLISH_CATALOG["STRUCT-TEST-THEATER"]
        self.assertIn("Verification Hierarchy", theater_exp["why_veterans_flag_it"])
        self.assertIn("Verification Hierarchy", theater_exp["fix_prompt"])
        self.assertIn("anti-slop-mutate", theater_exp["fix_prompt"])

        comment_exp = review.PLAIN_ENGLISH_CATALOG["STRUCT-COMMENTED-CODE"]
        self.assertIn("docs/evidence.md#ext-14", comment_exp["evidence"])
        self.assertIn("invariant", comment_exp["fix_prompt"].lower())

        # Plain-English and Markdown outputs render evidence Reference cleanly.
        sample_diff = _new_file_diff(
            "src/old.py",
            "# def old_fn(x):\n#     if x > 0:\n#         return x\n#     return 0\n\ndef live():\n    return 1\n",
        )
        rep = review.review_diff(sample_diff, repo_root=None)
        self.assertIn("STRUCT-COMMENTED-CODE", _codes(rep["warnings"]))
        plain_out = review.format_plain_english(rep, markdown=False)
        md_out = review.format_plain_english(rep, markdown=True)
        self.assertIn("Reference: docs/evidence.md#ext-14", plain_out)
        self.assertIn("- **Reference:** docs/evidence.md#ext-14", md_out)

    def test_review_cli_plain_english_markdown_json_and_diff_check_flags(self) -> None:
        (self.root / "src").mkdir()
        (self.root / "tests").mkdir()
        bad_prod = (
            "def compute():\n"
            "    try:\n"
            "        return risky()\n"
            "    except Exception:\n"
            "        return 0\n"
        )
        bad_test = "def test_fake():\n    assert True\n"
        (self.root / "src/app.py").write_text(bad_prod, encoding="utf-8")
        (self.root / "tests/test_app.py").write_text(bad_test, encoding="utf-8")

        diff_txt = _new_file_diff("src/app.py", bad_prod) + _new_file_diff("tests/test_app.py", bad_test)
        diff_file = self.root / "pr.diff"
        diff_file.write_text(diff_txt, encoding="utf-8")

        # 1. diff_check.py --structural --explain warns (exit 0) and prints plain-English rationale.
        proc_warn = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/diff_check.py"),
                "--diff", str(diff_file), "--repo-root", str(self.root),
                "--allow-test-edit", "--no-budget", "--structural", "--explain",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_warn.returncode, 0, msg=proc_warn.stderr)
        self.assertIn("STRUCT-SILENT-FALLBACK", proc_warn.stderr)
        self.assertIn("STRUCT-TEST-THEATER", proc_warn.stderr)
        self.assertIn("why it matters:", proc_warn.stderr)
        self.assertIn("how it compounds:", proc_warn.stderr)

        # 2. diff_check.py --strict-structural promotes structural warnings to exit 1.
        proc_strict = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/diff_check.py"),
                "--diff", str(diff_file), "--repo-root", str(self.root),
                "--allow-test-edit", "--no-budget", "--strict-structural", "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_strict.returncode, 1)
        strict_data = json.loads(proc_strict.stdout)
        self.assertFalse(strict_data["ok"])
        self.assertIn("STRUCT-SILENT-FALLBACK", _codes(strict_data["errors"]))
        self.assertIn("STRUCT-TEST-THEATER", _codes(strict_data["errors"]))

        # 3. gates/review.py --markdown + --json + --fail-on-warning
        proc_rev = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/review.py"),
                "--diff", str(diff_file), "--repo-root", str(self.root),
                "--markdown", "--fail-on-warning",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_rev.returncode, 1)
        self.assertIn("## Anti-Slop Plain-English Review", proc_rev.stdout)
        self.assertIn("Why experienced engineers flag this", proc_rev.stdout)
        self.assertIn("How it compounds in future AI turns", proc_rev.stdout)

        proc_rev_json = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/review.py"),
                "--diff", str(diff_file), "--repo-root", str(self.root), "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_rev_json.returncode, 0)
        rev_data = json.loads(proc_rev_json.stdout)
        self.assertEqual(rev_data["summary"]["compounding_risk_count"], 2)
        self.assertTrue(all("explanation" in w for w in rev_data["warnings"]))

    def test_review_cli_auto_reads_git_working_tree_diff(self) -> None:
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "ci@example.com"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "CI"], cwd=self.root, check=True)
        (self.root / "src").mkdir()
        (self.root / "src/clean.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=self.root, check=True)

        # Clean working tree -> exits 0 with clean message.
        proc_clean = subprocess.run(
            [sys.executable, "-B", str(REPO_ROOT / "gates/review.py"), "--repo-root", str(self.root)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
        )
        # Note: stdin is DEVNULL (non-tty empty), so pass explicit git diff via working tree check by checking --base or edited file.
        self.assertEqual(proc_clean.returncode, 0, msg=proc_clean.stderr)
        self.assertIn("Clean", proc_clean.stdout)

        # Modify file with a debug leftover and verify auto-git-diff detection (even with DEVNULL stdin).
        (self.root / "src/clean.py").write_text(
            "def add(a, b):\n    breakpoint()\n    return a + b\n",
            encoding="utf-8",
        )
        proc_auto = subprocess.run(
            [sys.executable, "-B", str(REPO_ROOT / "gates/review.py"), "--repo-root", str(self.root)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_auto.returncode, 1)
        self.assertIn("DIFF-DEBUG-LEFTOVER", proc_auto.stdout)

        proc_dirty = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/review.py"),
                "--repo-root", str(self.root), "--files", "src/clean.py",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_dirty.returncode, 1)
        self.assertIn("DIFF-DEBUG-LEFTOVER", proc_dirty.stdout)

        # Untracked newly created files must be reviewed automatically (unless --no-untracked).
        (self.root / "src/clean.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        (self.root / "tests").mkdir()
        (self.root / "tests/test_new_feature.py").write_text(
            "def test_untracked_theater():\n    assert True\n",
            encoding="utf-8",
        )
        proc_untracked = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/review.py"),
                "--repo-root", str(self.root), "--fail-on-warning",
            ],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_untracked.returncode, 1, msg=proc_untracked.stdout)
        self.assertIn("STRUCT-TEST-THEATER", proc_untracked.stdout)

        proc_no_untracked = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/review.py"),
                "--repo-root", str(self.root), "--no-untracked", "--fail-on-warning",
            ],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_no_untracked.returncode, 0, msg=proc_no_untracked.stdout)

    def test_structural_edge_cases_and_fail_closed_missing_learned_rules(self) -> None:
        # 1. Production obj.verify_*() / obj.check_*() calls without assertions are test theater.
        py_theater = "def test_auth_calls_verify():\n    auth.verify_token('tok')\n    svc.check_health()\n"
        self.assertEqual(
            len(structural.check_test_theater_in_source("tests/test_auth.py", py_theater)), 1
        )
        # Multiple JS/TS tautologies in one test block are still test theater.
        js_double_taut = "test('double', () => { expect(true).toBe(true); expect(1).toBe(1); });\n"
        self.assertEqual(
            len(structural.check_test_theater_in_source("src/auth.test.ts", js_double_taut)), 1
        )

        # 2. Keyword default=, 'or' env fallbacks, JS process.env || and numeric catch fallback.
        py_env = (
            "import os\n"
            "K1 = os.getenv('API_KEY', default='dev-only')\n"
            "K2 = os.environ.get('JWT_SECRET') or 'hardcoded'\n"
        )
        self.assertEqual(len(structural.check_silent_fallbacks_in_source("src/cfg.py", py_env)), 2)
        js_fb = (
            "const secret = process.env.JWT_SECRET || 'dev-secret';\n"
            "// const commented = process.env.API_KEY || 'ignored';\n"
            "function f() { try { return run(); } catch (e) { return -1; } }\n"
        )
        self.assertEqual(len(structural.check_silent_fallbacks_in_source("src/cfg.ts", js_fb)), 2)

        # 3. Same-name duplicated methods across two classes in same file + intra-file TS duplicate.
        py_cls_dup = (
            "class A:\n"
            "    def apply(self, items, rate):\n"
            "        total = 0\n"
            "        for it in items:\n"
            "            if it <= 0:\n"
            "                raise ValueError('bad')\n"
            "            total += it * rate\n"
            "        fee = (total * 5 + 50) // 100\n"
            "        return total + fee\n\n"
            "class B:\n"
            "    def apply(self, rows, bps):\n"
            "        amt = 0\n"
            "        for row in rows:\n"
            "            if row <= 0:\n"
            "                raise ValueError('bad')\n"
            "            amt += row * bps\n"
            "        tax = (amt * 5 + 50) // 100\n"
            "        return amt + tax\n"
        )
        self.assertEqual(len(structural.check_duplicate_blocks({"src/svc.py": (py_cls_dup, None)})), 1)
        ts_blk = (
            "  let total = 0;\n"
            "  for (const item of items) {\n"
            "    if (item.qty <= 0) { throw new Error('invalid quantity'); }\n"
            "    total += item.unitCents * item.qty;\n"
            "  }\n"
            "  const tax = Math.round((total * taxBps) / 10000);\n"
            "  return { subtotal: total, tax, total: total + tax };\n"
        )
        ts_dup = f"export function a(items, taxBps) {{\n{ts_blk}}}\nexport function b(items, taxBps) {{\n{ts_blk}}}\n"
        self.assertGreaterEqual(
            len(structural.check_duplicate_blocks({"src/calc.ts": (ts_dup, None)})), 1
        )

        # 4. Dead compat catches class methods + ignores non-boolean legacy_path + respects extra_sources over stale disk.
        cls_dead = (
            "class Svc:\n"
            "    def charge(self, amt, allow_legacy_fee=False):\n"
            "        return amt\n"
            "    def compute_legacy(self, x):\n"
            "        return x * 2\n"
            "    def inspect(self, legacy_path=None):\n"
            "        return legacy_path\n"
        )
        cls_hits = structural.check_dead_compat_in_source("src/svc.py", cls_dead)
        self.assertEqual(len(cls_hits), 2, msg=cls_hits)
        self.assertEqual({h["meta"]["kind"] for h in cls_hits}, {"legacy_param", "dead_legacy_symbol"})

        # Stale on-disk caller must not hide a dead legacy symbol when extra_sources has updated caller.
        (self.root / "src").mkdir(exist_ok=True)
        (self.root / "src/caller.py").write_text("legacy_fn()\n", encoding="utf-8")
        stale_hits = structural.check_dead_compat_in_source(
            "src/def.py",
            "def legacy_fn():\n    return 1\n",
            repo_root=self.root,
            extra_sources={"src/caller.py": "# removed caller\n"},
        )
        self.assertEqual(len(stale_hits), 1)

        # 5. Go god-function detected cleanly.
        go_src = "package main\nfunc giant() int {\n" + "    x := 1\n" * 65 + "    return x\n}\n"
        self.assertEqual(_codes(structural.check_god_growth_in_source("main.go", go_src)), {"STRUCT-GOD-FUNCTION"})

        # 6. Explicit nonexistent --learned-rules fails closed (exit 2) in both review.py and diff_check.py.
        missing = str(self.root / "does-not-exist.json")
        (self.root / "src/ok.py").write_text("x = 1\n", encoding="utf-8")
        p_rev = subprocess.run(
            [sys.executable, "-B", str(REPO_ROOT / "gates/review.py"), "--files", "src/ok.py", "--repo-root", str(self.root), "--learned-rules", missing],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_rev.returncode, 2)
        p_dc = subprocess.run(
            [sys.executable, "-B", str(REPO_ROOT / "gates/diff_check.py"), "--files", "src/ok.py", "--repo-root", str(self.root), "--learned-rules", missing],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_dc.returncode, 2)

    def test_oss_audit_precision_regressions_for_test_theater(self) -> None:
        # 1. Vitest / expect-type compile-time assertions (hono audit regression) are valid tests.
        ts_type_test = (
            "describe('types', () => {\n"
            "  it('checks recursive type', () => {\n"
            "    type Actual = JSONParsed<JSONValue>\n"
            "    expectTypeOf<Actual>().toExtend<JSONValue>()\n"
            "  })\n"
            "  it('checks assertType', () => {\n"
            "    assertType<string>('ok')\n"
            "  })\n"
            "  it('checks expect.soft', () => {\n"
            "    expect.soft(1 + 1).toBe(2)\n"
            "  })\n"
            "})\n"
        )
        self.assertEqual(
            structural.check_test_theater_in_source("src/types.test.ts", ts_type_test),
            [],
        )

        # 2. warnings.simplefilter('error', ...) is a real assertion (urllib3 audit regression),
        # while warnings.simplefilter('ignore', ...) without assertions is STILL test theater.
        py_warn_err = (
            "import warnings\n\n"
            "def test_no_deprecation():\n"
            "    with warnings.catch_warnings():\n"
            "        warnings.simplefilter('error', FutureWarning)\n"
            "        run_request()\n"
        )
        self.assertEqual(
            structural.check_test_theater_in_source("tests/test_warn.py", py_warn_err),
            [],
        )
        py_warn_ignore = (
            "import warnings\n\n"
            "def test_ignores_warning_without_assert():\n"
            "    with warnings.catch_warnings():\n"
            "        warnings.simplefilter('ignore', FutureWarning)\n"
            "        run_request()\n"
        )
        self.assertEqual(
            len(structural.check_test_theater_in_source("tests/test_warn.py", py_warn_ignore)),
            1,
        )

        # 3. Same-file and imported tests/util.py AST-verified helpers pass (tomlkit audit regression),
        # while an imported helper with ZERO assertions is STILL flagged as test theater.
        (self.root / "tests").mkdir(exist_ok=True)
        (self.root / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (self.root / "tests" / "util.py").write_text(
            "def elementary_test(val, typ, expected):\n"
            "    assert isinstance(val, typ)\n"
            "    assert val == expected\n\n"
            "def noop_helper(val):\n"
            "    return val\n",
            encoding="utf-8",
        )
        py_helper_ok = (
            "from tests.util import elementary_test\n\n"
            "def local_check(x):\n"
            "    assert x > 0\n\n"
            "def test_imported_helper():\n"
            "    elementary_test(42, int, 42)\n\n"
            "def test_local_helper():\n"
            "    local_check(5)\n"
        )
        self.assertEqual(
            structural.check_test_theater_in_source(
                "tests/test_items.py", py_helper_ok, repo_root=self.root
            ),
            [],
        )
        py_helper_bad = (
            "from tests.util import noop_helper\n\n"
            "def local_noop(x):\n"
            "    return x + 1\n\n"
            "def test_imported_noop():\n"
            "    noop_helper(42)\n\n"
            "def test_local_noop():\n"
            "    local_noop(5)\n"
        )
        bad_hits = structural.check_test_theater_in_source(
            "tests/test_items.py", py_helper_bad, repo_root=self.root
        )
        self.assertEqual(len(bad_hits), 2, msg=bad_hits)

        # 4. Module-attribute imported helpers (`import tests.util`, `from tests import util as u`)
        # and 1-hop re-exports (`tests/__init__.py`) verify via AST while assertion-free helpers still fail.
        (self.root / "tests" / "__init__.py").write_text(
            "from .util import elementary_test\n",
            encoding="utf-8",
        )
        py_mod_attr_ok = (
            "import tests.util\n"
            "from tests import util as u\n"
            "from tests import elementary_test\n\n"
            "def test_dotted():\n    tests.util.elementary_test(1, int, 1)\n"
            "def test_alias():\n    u.elementary_test(2, int, 2)\n"
            "def test_reexport():\n    elementary_test(3, int, 3)\n"
        )
        self.assertEqual(
            structural.check_test_theater_in_source(
                "tests/test_attr.py", py_mod_attr_ok, repo_root=self.root
            ),
            [],
        )
        py_mod_attr_bad = "import tests.util\ndef test_bad_attr():\n    tests.util.noop_helper(1)\n"
        self.assertEqual(
            len(
                structural.check_test_theater_in_source(
                    "tests/test_attr.py", py_mod_attr_bad, repo_root=self.root
                )
            ),
            1,
        )

        # 5. Deno @std/assert camelCase assertions (hono audit regression) pass, while empty Deno tests fail.
        deno_ok = (
            "Deno.test('escape elements', () => {\n"
            "  assertEquals(render(), '<div>ok</div>')\n"
            "})\n"
            "Deno.test('reject invalid', () => {\n"
            "  assertThrows(() => parse('bad'), Error)\n"
            "})\n"
        )
        self.assertEqual(
            structural.check_test_theater_in_source("runtime-tests/jsx.test.tsx", deno_ok),
            [],
        )
        deno_bad = "Deno.test('no assert', () => {\n  render()\n})\n"
        self.assertEqual(
            len(structural.check_test_theater_in_source("runtime-tests/jsx.test.tsx", deno_bad)),
            1,
        )

        # 6. Hunk-only mode (repo_root=None) must NOT false-positive on truncated Python or JS/TS test hunks
        # (urllib3 e8a81de5e1 regression), while complete empty tests in a new file remain flagged.
        trunc_py_diff = (
            "diff --git a/tests/test_socket.py b/tests/test_socket.py\n"
            "--- a/tests/test_socket.py\n"
            "+++ b/tests/test_socket.py\n"
            "@@ -10,4 +10,5 @@ class TestProxy:\n"
            " def test_simple(self):\n"
            "     cfg = make_cfg()\n"
            "+    cfg['strip_fragment'] = True\n"
            "     run_req(cfg)\n"
        )
        self.assertEqual(
            structural.check_structural_diff(trunc_py_diff, repo_root=None)["warnings"],
            [],
        )
        trunc_ts_diff = (
            "diff --git a/src/app.test.ts b/src/app.test.ts\n"
            "--- a/src/app.test.ts\n"
            "+++ b/src/app.test.ts\n"
            "@@ -5,3 +5,4 @@ describe('app', () => {\n"
            "   it('handles req', async () => {\n"
            "+    const h = makeHeaders()\n"
            "     await fetch(h)\n"
        )
        self.assertEqual(
            structural.check_structural_diff(trunc_ts_diff, repo_root=None)["warnings"],
            [],
        )

        # 7. TypeScript overload signatures & `declare function` must not miscount lines in STRUCT-GOD-FUNCTION.
        ts_overloads = "\n".join(
            [
                "export function parse(x: string): string;",
                "export function parse(x: number): number;",
                "export declare function external(opts: { a: number }): void;",
            ]
            + [f"export const ITEM_{i} = {i};" for i in range(45)]
            + ["export function parse(x: string | number): string | number {"]
            + [f"  const v{i} = x;" for i in range(20)]
            + ["  return x;", "}"]
        )
        self.assertEqual(
            structural.check_god_growth_in_source("src/parser.ts", ts_overloads, max_func_lines=60),
            [],
        )

        # 8. STRUCT-DEAD-COMPAT allows __all__-exported symbols & domain verbs like prune_old_sessions,
        # while still catching unreferenced calculate_old / calculate_legacy.
        py_active_old = (
            '__all__ = ["prune_old_sessions", "legacy_public_api"]\n'
            "def prune_old_sessions(items):\n    return [x for x in items if x]\n"
            "def legacy_public_api(x):\n    return x\n"
        )
        self.assertEqual(
            structural.check_dead_compat_in_source("src/cleanup.py", py_active_old),
            [],
        )
        self.assertEqual(
            len(
                structural.check_dead_compat_in_source(
                    "src/cleanup.py", "def calculate_old(x):\n    return x\n"
                )
            ),
            1,
        )

        # 9. gates/review.py invoked from a git subdirectory resolves git toplevel and enforces learned rules,
        # and PLAIN_ENGLISH_CATALOG stays free of em-dashes.
        for code, exp in review.PLAIN_ENGLISH_CATALOG.items():
            for field, val in exp.items():
                self.assertNotIn("\u2014", val, msg=(code, field))

        from gates import learn as _learn

        sub_repo = self.root / "subrepo"
        sub_repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=sub_repo, check=True)
        subprocess.run(["git", "config", "user.email", "ci@example.com"], cwd=sub_repo, check=True)
        subprocess.run(["git", "config", "user.name", "CI"], cwd=sub_repo, check=True)
        (sub_repo / "pkg").mkdir()
        (sub_repo / "pkg/mod.py").write_text("X = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=sub_repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=sub_repo, check=True)

        store = _learn.default_store_path(sub_repo)
        ent = _learn.capture_pattern(
            store,
            title="Ban raw_eval",
            bad_example="raw_eval(x)",
            desired_outcome="Use safe_parse",
            valid_neighbouring_case="safe_parse(x)",
        )
        _learn.propose_prevention(
            store, ent["id"], layer="deterministic_check", severity="error",
            file_glob="*.py", pattern=r"\braw_eval\s*\(",
            remediation="Use safe_parse.", retirement_trigger="Later.",
        )
        _learn.verify_rule(store, ent["id"], repo_root=sub_repo)
        _learn.approve_rule(store, ent["id"], approved_by="reviewer")

        (sub_repo / "pkg/mod.py").write_text("raw_eval('1')\n", encoding="utf-8")
        p_sub_diff = subprocess.run(
            [sys.executable, "-B", str(REPO_ROOT / "gates/review.py"), "--json"],
            cwd=sub_repo / "pkg", stdin=subprocess.DEVNULL,
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_sub_diff.returncode, 1, msg=p_sub_diff.stdout + p_sub_diff.stderr)
        self.assertIn("LEARNED-L-001", p_sub_diff.stdout)

        p_sub_files = subprocess.run(
            [sys.executable, "-B", str(REPO_ROOT / "gates/review.py"), "--json", "mod.py"],
            cwd=sub_repo / "pkg", stdin=subprocess.DEVNULL,
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_sub_files.returncode, 1, msg=p_sub_files.stdout + p_sub_files.stderr)
        self.assertIn("LEARNED-L-001", p_sub_files.stdout)


if __name__ == "__main__":
    unittest.main()
