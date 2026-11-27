"""Stdlib-only tests for diff-scoped AST mutation testing CLI (`gates/mutate.py`)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gates import mutate  # noqa: E402


MUTATE_SCRIPT = REPO_ROOT / "gates/mutate.py"


def _snapshot_tree(root: Path) -> dict[str, str]:
    snap: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root)).replace("\\", "/")
        if rel.startswith(".git/") or rel == ".git":
            continue
        if p.is_file():
            snap[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        elif p.is_dir():
            snap[rel + "/"] = "<dir>"
    return snap


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=root, check=True)


class MutateUnitTests(unittest.TestCase):
    def test_parse_file_target_spec(self) -> None:
        self.assertEqual(mutate.parse_file_target_spec("src/calc.py"), ("src/calc.py", None))
        self.assertEqual(mutate.parse_file_target_spec("src/calc.py:12"), ("src/calc.py", {12}))
        self.assertEqual(
            mutate.parse_file_target_spec("src/calc.py:3-5,10"),
            ("src/calc.py", {3, 4, 5, 10}),
        )
        with self.assertRaises(ValueError):
            mutate.parse_file_target_spec("src/calc.py:10-5")
        with self.assertRaises(ValueError):
            mutate.parse_file_target_spec("src/calc.py:0")

    def test_generate_scoped_mutants_operators_and_arid_suppression(self) -> None:
        src = (
            '"""Module docstring with 1 + 2 == 3."""\n'
            "import logging\n"
            "from typing import TYPE_CHECKING\n\n"
            "if TYPE_CHECKING:\n"
            "    HINT = 1 + 2\n\n"
            "def price(qty: int, unit_cents: int, vip: bool) -> int:\n"
            '    """Compute price."""\n'
            "    logging.info('pricing %d', qty + 1)\n"
            "    if qty <= 0:\n"
            "        raise ValueError('bad qty')\n"
            "    subtotal = qty * unit_cents\n"
            "    if vip and subtotal >= 1000:\n"
            "        subtotal = subtotal - 100\n"
            "    active = True\n"
            "    if not active:\n"
            "        return None\n"
            "    label = 'USD ' + 'cents'\n"
            "    return subtotal\n\n"
            'if __name__ == "__main__":\n'
            "    print(price(1, 100, False))\n"
        )
        mutants = mutate.generate_scoped_mutants("src/pricing.py", src, max_per_file=40)
        operators = {m["operator"] for m in mutants}
        self.assertEqual(
            operators,
            {"condition", "compare", "validation", "return_value", "arithmetic", "boolean", "boundary"},
        )
        mutated_lines = {m["line"] for m in mutants}
        # Arid lines (docstring=1, TYPE_CHECKING=5-6, logging.info=10, string concat=19, __main__=22-23) excluded.
        for arid_ln in (1, 5, 6, 10, 19, 22, 23):
            self.assertNotIn(arid_ln, mutated_lines, msg=f"Arid line {arid_ln} should not be mutated")
        for m in mutants:
            self.assertTrue(m["original_line"])
            self.assertTrue(m["mutated_line"])

        # Line-scoped generation strictly restricts to requested lines.
        scoped = mutate.generate_scoped_mutants("src/pricing.py", src, target_lines={11, 12})
        self.assertTrue(scoped)
        self.assertTrue({m["line"] for m in scoped}.issubset({11, 12}))


class MutateIntegrationCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _write_sample_repo(self, *, strong_tests: bool = True, failing_baseline: bool = False) -> None:
        (self.root / "pkg").mkdir(exist_ok=True)
        (self.root / "tests").mkdir(exist_ok=True)
        (self.root / "pkg/__init__.py").write_text("", encoding="utf-8")
        (self.root / "tests/__init__.py").write_text("", encoding="utf-8")

        base_calc = (
            "def legacy_untested(x):\n"
            "    if x > 10:\n"
            "        return x * 2\n"
            "    return x + 1\n"
        )
        (self.root / "pkg/calc.py").write_text(base_calc, encoding="utf-8")
        (self.root / "tests/test_calc.py").write_text(
            "import unittest\nfrom pkg.calc import legacy_untested\n\n"
            "class CalcTests(unittest.TestCase):\n"
            "    def test_placeholder(self):\n"
            "        self.assertIsNotNone(legacy_untested)\n",
            encoding="utf-8",
        )
        _init_git_repo(self.root)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=self.root, check=True)

        # Now add a new function on lines 6..15 in the working-tree diff!
        updated_calc = (
            base_calc
            + "\n"
            + "def compute_total(qty, unit_cents, discount_ok):\n"
            + "    if qty <= 0:\n"
            + "        raise ValueError('qty must be positive')\n"
            + "    total = qty * unit_cents\n"
            + "    if discount_ok and total >= 1000:\n"
            + "        total = total - 100\n"
            + "    return total\n"
        )
        (self.root / "pkg/calc.py").write_text(updated_calc, encoding="utf-8")

        if failing_baseline:
            test_src = (
                "import unittest\nfrom pkg.calc import compute_total\n\n"
                "class CalcTests(unittest.TestCase):\n"
                "    def test_broken(self):\n"
                "        self.assertEqual(compute_total(2, 500, False), 999999)\n"
            )
        elif strong_tests:
            test_src = (
                "import unittest\nfrom pkg.calc import compute_total\n\n"
                "class CalcTests(unittest.TestCase):\n"
                "    def test_rejects_zero_and_negative_qty(self):\n"
                "        with self.assertRaises(ValueError):\n"
                "            compute_total(0, 100, False)\n"
                "        with self.assertRaises(ValueError):\n"
                "            compute_total(-2, 100, False)\n\n"
                "    def test_exact_discount_boundary_and_math(self):\n"
                "        self.assertEqual(compute_total(2, 500, True), 900)\n"
                "        self.assertEqual(compute_total(2, 500, False), 1000)\n"
                "        self.assertEqual(compute_total(1, 999, True), 999)\n"
                "        self.assertEqual(compute_total(3, 400, False), 1200)\n"
            )
        else:
            # Weak / theater test: calls function once with minimal check, misses boundaries & errors.
            test_src = (
                "import unittest\nfrom pkg.calc import compute_total\n\n"
                "class CalcTests(unittest.TestCase):\n"
                "    def test_theater(self):\n"
                "        compute_total(1, 100, False)\n"
                "        self.assertTrue(True)\n"
            )
        (self.root / "tests/test_calc.py").write_text(test_src, encoding="utf-8")

    def test_strong_tests_diff_scoped_kill_mutants_and_never_mutate_working_tree(self) -> None:
        self._write_sample_repo(strong_tests=True)
        before_snap = _snapshot_tree(self.root)

        proc = subprocess.run(
            [
                sys.executable, "-B", str(MUTATE_SCRIPT),
                "--repo-root", str(self.root),
                "--json",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        after_snap = _snapshot_tree(self.root)
        # Working tree must be byte-for-byte untouched (and no __pycache__ created).
        self.assertEqual(before_snap, after_snap)

        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["exit_code"], 0)
        self.assertTrue(data["baseline"]["passed"])
        self.assertEqual(data["scope"]["files_targeted"], ["pkg/calc.py"])
        self.assertGreater(data["summary"]["mutants_tested"], 0)
        self.assertGreaterEqual(data["summary"]["kill_rate"], 0.65)
        self.assertEqual(data["summary"]["survived"], 0)

        # Diff-scoping: EVERY mutant must be on newly added lines (>= 6), NEVER on legacy_untested (lines 1..4).
        all_muts = data["killed_mutants"] + data["survived_mutants"]
        self.assertTrue(all(m["line"] >= 6 for m in all_muts), msg=all_muts)

    def test_weak_theater_tests_let_mutants_survive_and_report_exact_lines(self) -> None:
        self._write_sample_repo(strong_tests=False)
        before_snap = _snapshot_tree(self.root)

        proc_json = subprocess.run(
            [
                sys.executable, "-B", str(MUTATE_SCRIPT),
                "--repo-root", str(self.root),
                "--json",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(before_snap, _snapshot_tree(self.root))
        self.assertEqual(proc_json.returncode, 1, msg=proc_json.stdout + proc_json.stderr)
        data = json.loads(proc_json.stdout)
        self.assertFalse(data["ok"])
        self.assertEqual(data["exit_code"], 1)
        self.assertGreater(data["summary"]["survived"], 0)
        self.assertLess(data["summary"]["kill_rate"], 0.65)
        for surv in data["survived_mutants"]:
            self.assertEqual(surv["file"], "pkg/calc.py")
            self.assertGreaterEqual(surv["line"], 6)
            self.assertTrue(surv["original_line"])
            self.assertTrue(surv["mutated_line"])
            self.assertNotEqual(surv["original_line"], surv["mutated_line"])

        # Plain-English report lists exact file:line, Original, and Mutated lines (and zero em-dashes).
        proc_txt = subprocess.run(
            [
                sys.executable, "-B", str(MUTATE_SCRIPT),
                "--repo-root", str(self.root),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc_txt.returncode, 1)
        self.assertIn("Baseline tests: PASSED", proc_txt.stdout)
        self.assertIn("Survived Mutants (Test Suite Blind Spots)", proc_txt.stdout)
        self.assertIn("pkg/calc.py:", proc_txt.stdout)
        self.assertIn("Original:", proc_txt.stdout)
        self.assertIn("Mutated:", proc_txt.stdout)
        self.assertNotIn("\u2014", proc_txt.stdout)

        # Report-only mode (--min-kill-rate 0) exits 0 while still showing survived mutants.
        proc_ro = subprocess.run(
            [
                sys.executable, "-B", str(MUTATE_SCRIPT),
                "--repo-root", str(self.root),
                "--min-kill-rate", "0",
                "--markdown",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc_ro.returncode, 0, msg=proc_ro.stdout + proc_ro.stderr)
        self.assertIn("## Anti-Slop Diff-Scoped Mutation Report", proc_ro.stdout)
        self.assertIn("### Survived Mutants", proc_ro.stdout)

    def test_failing_baseline_exits_2_cleanly(self) -> None:
        self._write_sample_repo(failing_baseline=True)
        proc = subprocess.run(
            [
                sys.executable, "-B", str(MUTATE_SCRIPT),
                "--repo-root", str(self.root),
                "--json",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 2, msg=proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertFalse(data["ok"])
        self.assertEqual(data["exit_code"], 2)
        self.assertFalse(data["baseline"]["passed"])
        self.assertIn("Baseline tests failed", data["baseline"]["error"])

    def test_zero_mutable_changed_lines_exits_0_and_files_line_range_works(self) -> None:
        self._write_sample_repo(strong_tests=True)
        # Diff touching only README.md -> 0 mutable Python lines -> exit 0.
        docs_diff = (
            "diff --git a/README.md b/README.md\n"
            "--- /dev/null\n"
            "+++ b/README.md\n"
            "@@ -0,0 +1,1 @@\n"
            "+# Notes\n"
        )
        proc_zero = subprocess.run(
            [
                sys.executable, "-B", str(MUTATE_SCRIPT),
                "--repo-root", str(self.root),
                "--diff", "-",
                "--json",
            ],
            input=docs_diff,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc_zero.returncode, 0, msg=proc_zero.stdout + proc_zero.stderr)
        zdata = json.loads(proc_zero.stdout)
        self.assertTrue(zdata["ok"])
        self.assertEqual(zdata["summary"]["mutants_tested"], 0)
        self.assertIsNone(zdata["summary"]["kill_rate"])

        # Explicit --files with :START-END line range mutates ONLY lines 6-15 and caps at --max-mutants.
        proc_files = subprocess.run(
            [
                sys.executable, "-B", str(MUTATE_SCRIPT),
                "--repo-root", str(self.root),
                "--files", "pkg/calc.py:6-15",
                "--max-mutants", "4",
                "--test-cmd", f"{sys.executable} -B -m unittest discover -s tests",
                "--json",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc_files.returncode, 0, msg=proc_files.stdout + proc_files.stderr)
        fdata = json.loads(proc_files.stdout)
        self.assertEqual(fdata["mode"], "files")
        self.assertLessEqual(fdata["summary"]["mutants_tested"], 4)
        self.assertTrue(all(6 <= m["line"] <= 15 for m in fdata["killed_mutants"]))

    def test_mutant_timeout_counts_as_killed_and_timed_out(self) -> None:
        (self.root / "loopmod.py").write_text(
            "def count_down(n):\n"
            "    total = 0\n"
            "    while n > 0:\n"
            "        total += 1\n"
            "        n -= 1\n"
            "    return total\n",
            encoding="utf-8",
        )
        (self.root / "test_loop.py").write_text(
            "import unittest\nfrom loopmod import count_down\n\n"
            "class LoopTests(unittest.TestCase):\n"
            "    def test_count(self):\n"
            "        self.assertEqual(count_down(3), 3)\n",
            encoding="utf-8",
        )
        # Mutating `while n > 0:` -> `while not (n > 0):` or `n -= 1` -> `n` boundary causes quick kill or timeout;
        # specifically `while n > 0:` -> `while n >= 0:` loops infinitely on `n == 0`? No, n goes -1.
        # Mutating `n > 0` with `n = n - 1` -> `n = n + 1` (line 5) causes infinite loop!
        (self.root / "loopmod.py").write_text(
            "def count_down(n):\n"
            "    total = 0\n"
            "    while n > 0:\n"
            "        total = total + 1\n"
            "        n = n - 1\n"
            "    return total\n",
            encoding="utf-8",
        )
        res = mutate.run_diff_mutation(
            self.root,
            {"loopmod.py": {5}},
            test_cmd=[sys.executable, "-B", "-m", "unittest", "discover"],
            max_mutants=4,
            timeout_s=0.4,
            min_kill_rate=0.5,
            mode="files",
        )
        self.assertTrue(res["ok"], msg=res)
        self.assertGreaterEqual(res["summary"]["timed_out"], 1)
        self.assertEqual(res["summary"]["survived"], 0)


if __name__ == "__main__":
    unittest.main()
