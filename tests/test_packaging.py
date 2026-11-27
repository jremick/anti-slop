"""Stdlib-only tests for packaging, GitHub Action, pre-commit, trust metadata,
`diff_check.py --no-budget`, and `run_diff_gate_hook.py --install`.
"""

from __future__ import annotations

import importlib
import importlib.resources
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 (e.g., macOS system python3 3.9)
    tomllib = None
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
DIFF_CHECK_SCRIPT = REPO_ROOT / "gates/diff_check.py"
HOOK_SCRIPT = REPO_ROOT / "gates/hooks/run_diff_gate_hook.py"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _codes(items) -> set[str]:
    return {item["code"] for item in items}


def _extract_json_block(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    assert start != -1 and end != -1 and end > start, f"No JSON object found in:\n{text}"
    return json.loads(text[start : end + 1])


class PackagingMetadataTests(unittest.TestCase):
    def test_pyproject_toml_metadata_and_console_entry_points(self) -> None:
        pyproject_path = REPO_ROOT / "pyproject.toml"
        self.assertTrue(pyproject_path.is_file())
        raw_text = pyproject_path.read_text(encoding="utf-8")
        expected_scripts = {
            "anti-slop": "gates.cli:main",
            "anti-slop-diff": "gates.diff_check:main",
            "anti-slop-review": "gates.review:main",
            "anti-slop-learn": "gates.learn:main",
            "anti-slop-hook": "gates.hooks.run_diff_gate_hook:main",
            "anti-slop-api": "gates.api_checks:main",
            "anti-slop-mutate": "gates.mutate:main",
            "anti-slop-verify": "gates.verify:main",
        }
        if tomllib is not None:
            data = tomllib.loads(raw_text)
            project = data["project"]
            self.assertEqual(project["name"], "anti-slop")
            self.assertEqual(project["version"], "0.8.0")
            self.assertEqual(project["requires-python"], ">=3.11")
            self.assertEqual(project["dependencies"], [])

            lic = project["license"]
            if isinstance(lic, dict):
                self.assertEqual(lic.get("text"), "MIT")
            else:
                self.assertEqual(lic, "MIT")

            self.assertEqual(len(project["scripts"]), 8)
            self.assertEqual(project["scripts"], expected_scripts)

            setuptools_cfg = data.get("tool", {}).get("setuptools", {})
            packages = setuptools_cfg.get("packages", [])
            self.assertIn("gates", packages)
            self.assertIn("gates.hooks", packages)
            self.assertIn("library", packages)
            self.assertIn("skills", packages)

            pkg_data = setuptools_cfg.get("package-data", {})
            self.assertIn("catalog.json", pkg_data.get("library", []))
            self.assertIn("anti-slop/SKILL.md", pkg_data.get("skills", []))
        else:
            # Python < 3.11 fallback (stdlib-only verification without skipping)
            self.assertRegex(raw_text, r'(?m)^name\s*=\s*"anti-slop"\s*$')
            self.assertRegex(raw_text, r'(?m)^version\s*=\s*"0\.8\.0"\s*$')
            self.assertRegex(raw_text, r'(?m)^requires-python\s*=\s*">=3\.11"\s*$')
            self.assertRegex(raw_text, r"(?m)^dependencies\s*=\s*\[\s*\]\s*$")
            self.assertRegex(raw_text, r'(?m)^license\s*=\s*(?:\{\s*text\s*=\s*"MIT"\s*\}|"MIT")\s*$')
            for script_name, target in expected_scripts.items():
                self.assertIn(f'{script_name} = "{target}"', raw_text)
            self.assertIn('"gates"', raw_text)
            self.assertIn('"gates.hooks"', raw_text)
            self.assertIn('"library"', raw_text)
            self.assertIn('"skills"', raw_text)
            self.assertRegex(raw_text, r'(?m)^library\s*=\s*\[\s*"catalog\.json"\s*\]\s*$')
            self.assertIn('"anti-slop/SKILL.md"', raw_text)

        self.assertTrue((REPO_ROOT / "gates/__init__.py").is_file())
        self.assertTrue((REPO_ROOT / "gates/hooks/__init__.py").is_file())
        self.assertTrue((REPO_ROOT / "library/__init__.py").is_file())
        self.assertTrue((REPO_ROOT / "library/catalog.json").is_file())
        self.assertTrue((REPO_ROOT / "skills/__init__.py").is_file())
        self.assertTrue((REPO_ROOT / "skills/anti-slop/SKILL.md").is_file())
        self.assertTrue((REPO_ROOT / "skills/README.md").is_file())

        # Verify bundled skill loads cleanly through importlib.resources.
        bundled_skill = (
            importlib.resources.files("skills")
            .joinpath("anti-slop")
            .joinpath("SKILL.md")
            .read_text(encoding="utf-8")
        )
        self.assertIn("name: anti-slop", bundled_skill)

        # Verify every declared console script imports cleanly and resolves a callable.
        for script_name, target in expected_scripts.items():
            mod_name, attr_name = target.split(":", 1)
            with self.subTest(script=script_name, target=target):
                mod = importlib.import_module(mod_name)
                entry_fn = getattr(mod, attr_name, None)
                self.assertTrue(callable(entry_fn), msg=f"{target} is not callable")

    def test_action_yml_composite_schema_inputs_and_safe_env_indirection(self) -> None:
        action_path = REPO_ROOT / "action.yml"
        self.assertTrue(action_path.is_file())
        text = action_path.read_text(encoding="utf-8")

        self.assertRegex(text, r"using:\s*['\"]?composite['\"]?")
        self.assertIn("gates/diff_check.py", text)

        required_inputs = (
            "allow-test-edit",
            "allow-test-skip",
            "strict-prose",
            "no-budget",
            "max-net-loc",
            "max-files",
            "check-pr-body",
            "files",
            "structural",
            "strict-structural",
            "explain",
            "learned-rules",
            "exclude",
        )
        for inp in required_inputs:
            with self.subTest(input=inp):
                self.assertRegex(text, rf"(?m)^  {re.escape(inp)}:\s*$")

        # Security check: never interpolate ${{ inputs.* }} or PR body directly inside run: shell lines.
        run_idx = text.find("run: |")
        self.assertGreater(run_idx, 0)
        run_block = text[run_idx:]
        self.assertNotIn("${{ inputs.", run_block)
        self.assertNotIn("${{ github.event.", run_block)
        # Multi-line YAML `files: |` inputs must normalize newlines before splitting.
        self.assertIn("tr '\\r\\n' '  '", run_block)

    def test_action_yml_shell_handles_single_commit_multi_commit_and_files_mode(self) -> None:
        action_text = (REPO_ROOT / "action.yml").read_text(encoding="utf-8")
        marker = "      run: |\n"
        idx = action_text.find(marker)
        self.assertGreater(idx, 0)
        script_lines = [
            line[8:] if line.startswith("        ") else line
            for line in action_text[idx + len(marker) :].splitlines()
        ]
        bash_script = "\n".join(script_lines) + "\n"

        def _run_action(cwd: Path, **env_overrides: str) -> subprocess.CompletedProcess:
            env = os.environ.copy()
            env.update({
                "ACTION_PATH": str(REPO_ROOT),
                "INPUT_ALLOW_TEST_EDIT": "false",
                "INPUT_ALLOW_TEST_SKIP": "false",
                "INPUT_STRICT_PROSE": "false",
                "INPUT_NO_BUDGET": "true",
                "INPUT_MAX_NET_LOC": "400",
                "INPUT_MAX_FILES": "10",
                "INPUT_CHECK_PR_BODY": "false",
                "INPUT_FILES": "",
                "BASE_REF": "",
                "BASE_SHA": "",
                "BEFORE_SHA": "",
                "PR_BODY": "",
            })
            env.update(env_overrides)
            return subprocess.run(
                ["bash", "-c", bash_script],
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "ci@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "CI"], cwd=repo, check=True)
            (repo / "src").mkdir()
            (repo / "src/app.py").write_text("VALUE = 1\n", encoding="utf-8")
            (repo / "README.md").write_text("# Sample\n\nSee `src/app.py`.\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "Initial commit"], cwd=repo, check=True)

            # 1. Single-commit push (no HEAD~1): exits 0 cleanly with notice, no crash.
            single_res = _run_action(repo)
            self.assertEqual(single_res.returncode, 0, msg=single_res.stderr + single_res.stdout)
            self.assertIn("single-commit repository", single_res.stdout)

            # 2. Multi-line `files: |` mode inspects listed files directly.
            files_ok = _run_action(repo, INPUT_FILES="README.md\nsrc/app.py\n")
            self.assertEqual(files_ok.returncode, 0, msg=files_ok.stderr)

            # Whitespace-only `files` input gracefully falls through instead of argparse exit 2.
            ws_files = _run_action(repo, INPUT_FILES="   \n  ")
            self.assertEqual(ws_files.returncode, 0, msg=ws_files.stderr)

            # 3. Second commit with objective defect (`breakpoint()`) is caught via HEAD~1...HEAD.
            (repo / "src/app.py").write_text("def run():\n    breakpoint()\n", encoding="utf-8")
            subprocess.run(["git", "add", "src/app.py"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "Add debug leftover"], cwd=repo, check=True)

            dirty_res = _run_action(repo)
            self.assertEqual(dirty_res.returncode, 1, msg=dirty_res.stdout)
            self.assertIn("DIFF-DEBUG-LEFTOVER", dirty_res.stderr)

            # 3b. Opt-in structural / strict-structural / explain / learned-rules inputs remain off by default
            # and enforce when enabled.
            (repo / "src/app.py").write_text(
                "def calc(cents):\n"
                "    try:\n"
                "        return float(cents) / 100.0\n"
                "    except Exception:\n"
                "        return 0\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "src/app.py"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "Add silent fallback"], cwd=repo, check=True)

            # Default-off backward compatibility: exits 0 without structural or learned rules.
            compat_res = _run_action(repo)
            self.assertEqual(compat_res.returncode, 0, msg=compat_res.stderr)

            # Opt-in structural + explain emits warning + plain-English rationale, exits 0.
            struct_warn = _run_action(repo, INPUT_STRUCTURAL="true", INPUT_EXPLAIN="true")
            self.assertEqual(struct_warn.returncode, 0, msg=struct_warn.stderr)
            self.assertIn("STRUCT-SILENT-FALLBACK", struct_warn.stderr)
            self.assertIn("why it matters:", struct_warn.stderr)

            # Opt-in strict-structural fails with exit 1.
            struct_err = _run_action(repo, INPUT_STRICT_STRUCTURAL="true")
            self.assertEqual(struct_err.returncode, 1, msg=struct_err.stdout)
            self.assertIn("STRUCT-SILENT-FALLBACK", struct_err.stderr)

            # Opt-in learned-rules enforces an approved deterministic rule.
            learn_mod = importlib.import_module("gates.learn")
            store_path = repo / ".anti-slop" / "learned" / "rules.json"
            entry = learn_mod.capture_pattern(
                store_path,
                title="Float math on cents",
                bad_example="float(cents) / 100.0",
                desired_outcome="Keep cents as integer",
                valid_neighbouring_case="float(seconds) / 1000.0",
            )
            learn_mod.propose_prevention(
                store_path,
                entry["id"],
                layer="deterministic_check",
                severity="error",
                file_glob="*.py",
                pattern=r"\bfloat\s*\(\s*cents\s*\)",
                remediation="Use integer cents or Decimal.",
                retirement_trigger="Retire once static typing enforces integer cents.",
            )
            learn_mod.verify_rule(store_path, entry["id"], repo_root=repo, max_repo_hits=1)
            learn_mod.approve_rule(store_path, entry["id"], approved_by="ci-maintainer")

            learned_res = _run_action(repo, INPUT_LEARNED_RULES=".anti-slop/learned/rules.json")
            self.assertEqual(learned_res.returncode, 1, msg=learned_res.stdout)
            self.assertIn("LEARNED-L-001", learned_res.stderr)

            # 3c. Optional `exclude` input skips matched immutable artifacts/fixtures
            # without glob-expanding in bash, while non-excluded files still fail cleanly.
            (repo / "results/pilot-v0.7.0/artifacts/run1").mkdir(parents=True)
            (repo / "results/pilot-v0.7.0/artifacts/run1/stage-1.md").write_text(
                "Subject workspace modified `tests/test_promos.py`.\n",
                encoding="utf-8",
            )
            (repo / "benchmarks/sources/sample").mkdir(parents=True)
            (repo / "benchmarks/sources/sample/fixture.py").write_text(
                "def run():\n    breakpoint()\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "results", "benchmarks"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "Add benchmark artifacts and fixture"], cwd=repo, check=True)

            without_exclude = _run_action(repo)
            self.assertEqual(without_exclude.returncode, 1, msg=without_exclude.stdout)
            self.assertIn("DIFF-BROKEN-DOC-PATH", without_exclude.stderr)
            self.assertIn("DIFF-DEBUG-LEFTOVER", without_exclude.stderr)

            exclude_spec = "results/*/artifacts/**\nbenchmarks/sources/**\n"
            with_exclude = _run_action(repo, INPUT_EXCLUDE=exclude_spec)
            self.assertEqual(with_exclude.returncode, 0, msg=with_exclude.stderr + with_exclude.stdout)

            # Non-excluded file defect in the same commit still fails when exclude is active.
            (repo / "results/pilot-v0.7.0/artifacts/run1/stage-2.md").write_text(
                "Isolated transcript mentions `tests/test_refunds.py`.\n",
                encoding="utf-8",
            )
            (repo / "src/real_bug.py").write_text("def fail():\n    breakpoint()\n", encoding="utf-8")
            subprocess.run(["git", "add", "results", "src/real_bug.py"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "Add artifact plus non-excluded defect"], cwd=repo, check=True)

            non_excluded_fail = _run_action(repo, INPUT_EXCLUDE=exclude_spec)
            self.assertEqual(non_excluded_fail.returncode, 1, msg=non_excluded_fail.stdout)
            self.assertIn("DIFF-DEBUG-LEFTOVER", non_excluded_fail.stderr)
            self.assertIn("src/real_bug.py", non_excluded_fail.stderr)
            self.assertNotIn("DIFF-BROKEN-DOC-PATH", non_excluded_fail.stderr)

            # 4. Validate workflow tests Python 3.11-3.13 matrix, Node 24, and dogfoods `uses: ./`.
            wf_text = (REPO_ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
            for py_ver in ("'3.11'", "'3.12'", "'3.13'"):
                self.assertIn(py_ver, wf_text)
            self.assertIn("actions/setup-node@v4", wf_text)
            self.assertIn("node-version: '24'", wf_text)
            self.assertIn("dogfood-action:", wf_text)
            self.assertIn("uses: ./", wf_text)
            self.assertIn("persist-credentials: false", wf_text)
            self.assertIn("results/*/artifacts/**", wf_text)
            self.assertIn("benchmarks/sources/**", wf_text)

    def test_pre_commit_hooks_yaml_definition(self) -> None:
        hook_cfg = REPO_ROOT / ".pre-commit-hooks.yaml"
        self.assertTrue(hook_cfg.is_file())
        text = hook_cfg.read_text(encoding="utf-8")

        self.assertRegex(text, r"(?m)^-\s+id:\s+anti-slop-diff\s*$")
        self.assertRegex(text, r"(?m)^\s+entry:\s+anti-slop-diff\s*$")
        self.assertRegex(text, r"(?m)^\s+language:\s+python\s*$")
        self.assertIn("args: [--no-budget, --allow-test-edit]", text)
        self.assertRegex(text, r"(?m)^-\s+id:\s+anti-slop-diff-lock-tests\s*$")
        self.assertRegex(text, r"(?m)^-\s+id:\s+anti-slop-review\s*$")
        self.assertRegex(text, r"(?m)^\s+entry:\s+anti-slop-review\s*$")

        # Verify pre-commit positional invocation contract against gates/review.py directly.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            (tmp_root / "src").mkdir()
            (tmp_root / "src/clean.py").write_text("VALUE = 1\n", encoding="utf-8")
            (tmp_root / "src/dirty.py").write_text("def run():\n    breakpoint()\n", encoding="utf-8")
            proc_ok = subprocess.run(
                [sys.executable, "-B", str(REPO_ROOT / "gates/review.py"), "--repo-root", str(tmp_root), "src/clean.py"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc_ok.returncode, 0, msg=proc_ok.stderr + proc_ok.stdout)
            proc_fail = subprocess.run(
                [sys.executable, "-B", str(REPO_ROOT / "gates/review.py"), "--repo-root", str(tmp_root), "src/dirty.py"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc_fail.returncode, 1, msg=proc_fail.stdout)
            self.assertIn("DIFF-DEBUG-LEFTOVER", proc_fail.stdout)

    def test_security_and_third_party_licenses_docs(self) -> None:
        diff_check = importlib.import_module("gates.diff_check")
        sec_path = REPO_ROOT / "SECURITY.md"
        lic_path = REPO_ROOT / "THIRD_PARTY_LICENSES.md"
        self.assertTrue(sec_path.is_file())
        self.assertTrue(lic_path.is_file())

        res = diff_check.check_files(
            ["SECURITY.md", "THIRD_PARTY_LICENSES.md"],
            repo_root=REPO_ROOT,
        )
        self.assertTrue(res["ok"], msg=res["errors"])

        sec_text = sec_path.read_text(encoding="utf-8")
        self.assertIn("security/advisories/new", sec_text)
        self.assertIn("benchmarks/sources/", sec_text)

        lic_text = lic_path.read_text(encoding="utf-8")
        for suite in (
            "rw1_tomlkit",
            "rw2_markdown",
            "rw3_urllib3",
            "rw4_packaging_264",
            "rw5_sqlparse",
            "rw6_tomlkit_release",
        ):
            self.assertIn(suite, lic_text)
        self.assertIn("BSD-2-Clause", lic_text)
        self.assertIn("Apache-2.0", lic_text)
        self.assertIn("REF-01", lic_text)
        self.assertIn("REF-02", lic_text)

    def test_portable_hook_examples_and_ci_ratchet_templates(self) -> None:
        claude_data = json.loads(
            (REPO_ROOT / "gates/hooks/claude-settings.example.json").read_text(encoding="utf-8")
        )
        claude_cmds = [
            h["command"]
            for event in ("PreToolUse", "Stop")
            for entry in claude_data["hooks"][event]
            for h in entry["hooks"]
        ]
        for cmd in claude_cmds:
            self.assertIn("anti-slop-hook", cmd)
            self.assertIn("uvx", cmd)

        agy_data = json.loads(
            (REPO_ROOT / "gates/hooks/antigravity-hooks.example.json").read_text(encoding="utf-8")
        )
        agy_cmds = [
            h["command"]
            for group in agy_data["anti-slop-diff-gate"]["PreToolUse"]
            for h in group["hooks"]
        ] + [h["command"] for h in agy_data["anti-slop-diff-gate"]["Stop"]]
        for cmd in agy_cmds:
            self.assertIn("anti-slop-hook", cmd)
            self.assertIn("uvx", cmd)

        ci_text = (REPO_ROOT / "gates/ci-ratchet.yml").read_text(encoding="utf-8")
        repo_version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertIn(f"uses: jremick/anti-slop@v{repo_version}", ci_text)
        self.assertIn("uvx", ci_text)
        self.assertIn("gates/diff_check.py", ci_text)


class DiffCheckNoBudgetCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "src").mkdir()
        (self.root / "src/clean.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.root / "src/dirty.py").write_text("def f():\n    breakpoint()\n", encoding="utf-8")

    def test_no_budget_disables_loc_and_file_caps_but_keeps_defect_gates(self) -> None:
        large_clean_diff = self.root / "large_clean.diff"
        large_clean_diff.write_text(
            "diff --git a/src/large.py b/src/large.py\n"
            "--- /dev/null\n"
            "+++ b/src/large.py\n"
            "@@ -0,0 +1,420 @@\n"
            + "".join(f"+CONST_{i} = {i}\n" for i in range(420)),
            encoding="utf-8",
        )

        proc_default = subprocess.run(
            [
                sys.executable, "-B", str(DIFF_CHECK_SCRIPT),
                "--diff", str(large_clean_diff), "--repo-root", str(self.root), "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_default.returncode, 1)
        self.assertIn("DIFF-MAX-NET-LOC", _codes(json.loads(proc_default.stdout)["errors"]))

        proc_nobudget = subprocess.run(
            [
                sys.executable, "-B", str(DIFF_CHECK_SCRIPT),
                "--diff", str(large_clean_diff), "--repo-root", str(self.root), "--no-budget", "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_nobudget.returncode, 0, msg=proc_nobudget.stdout)
        self.assertTrue(json.loads(proc_nobudget.stdout)["ok"])

        # Exceeding default 10-file budget passes with --no-budget.
        many_files_diff = self.root / "many_files.diff"
        many_files_diff.write_text(
            "".join(
                f"diff --git a/src/m{i}.py b/src/m{i}.py\n"
                f"--- /dev/null\n+++ b/src/m{i}.py\n@@ -0,0 +1,1 @@\n+X = {i}\n"
                for i in range(12)
            ),
            encoding="utf-8",
        )
        proc_many_default = subprocess.run(
            [
                sys.executable, "-B", str(DIFF_CHECK_SCRIPT),
                "--diff", str(many_files_diff), "--repo-root", str(self.root), "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_many_default.returncode, 1)
        self.assertIn("DIFF-MAX-FILES", _codes(json.loads(proc_many_default.stdout)["errors"]))

        proc_many_nobudget = subprocess.run(
            [
                sys.executable, "-B", str(DIFF_CHECK_SCRIPT),
                "--diff", str(many_files_diff), "--repo-root", str(self.root), "--no-budget", "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_many_nobudget.returncode, 0, msg=proc_many_nobudget.stdout)

        # Objective defects (e.g. breakpoint()) are STILL blocked under --no-budget.
        large_dirty_diff = self.root / "large_dirty.diff"
        large_dirty_diff.write_text(
            "diff --git a/src/large_dirty.py b/src/large_dirty.py\n"
            "--- /dev/null\n"
            "+++ b/src/large_dirty.py\n"
            "@@ -0,0 +1,421 @@\n"
            + "".join(f"+CONST_{i} = {i}\n" for i in range(420))
            + "+breakpoint()\n",
            encoding="utf-8",
        )
        proc_dirty = subprocess.run(
            [
                sys.executable, "-B", str(DIFF_CHECK_SCRIPT),
                "--diff", str(large_dirty_diff), "--repo-root", str(self.root), "--no-budget", "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_dirty.returncode, 1)
        dirty_codes = _codes(json.loads(proc_dirty.stdout)["errors"])
        self.assertIn("DIFF-DEBUG-LEFTOVER", dirty_codes)
        self.assertNotIn("DIFF-MAX-NET-LOC", dirty_codes)

    def test_positional_file_paths_for_pre_commit_invocation(self) -> None:
        proc_ok = subprocess.run(
            [
                sys.executable, "-B", str(DIFF_CHECK_SCRIPT),
                "--no-budget", "--repo-root", str(self.root), "--json",
                "src/clean.py",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_ok.returncode, 0, msg=proc_ok.stdout)
        self.assertTrue(json.loads(proc_ok.stdout)["ok"])

        proc_fail = subprocess.run(
            [
                sys.executable, "-B", str(DIFF_CHECK_SCRIPT),
                "--no-budget", "--repo-root", str(self.root), "--json",
                "src/dirty.py",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_fail.returncode, 1)
        self.assertIn("DIFF-DEBUG-LEFTOVER", _codes(json.loads(proc_fail.stdout)["errors"]))

        # Pre-commit default args (--no-budget --allow-test-edit): clean test passes,
        # while @pytest.mark.skip is still blocked with DIFF-TEST-SKIP.
        (self.root / "tests").mkdir()
        (self.root / "tests/test_ok.py").write_text(
            "def test_ok():\n    assert 1 + 1 == 2\n",
            encoding="utf-8",
        )
        (self.root / "tests/test_skipped.py").write_text(
            "import pytest\n\n@pytest.mark.skip(reason='flaky')\ndef test_skip():\n    assert True\n",
            encoding="utf-8",
        )
        proc_test_ok = subprocess.run(
            [
                sys.executable, "-B", str(DIFF_CHECK_SCRIPT),
                "--no-budget", "--allow-test-edit", "--repo-root", str(self.root), "--json",
                "tests/test_ok.py",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_test_ok.returncode, 0, msg=proc_test_ok.stdout)
        self.assertTrue(json.loads(proc_test_ok.stdout)["ok"])

        proc_test_skip = subprocess.run(
            [
                sys.executable, "-B", str(DIFF_CHECK_SCRIPT),
                "--no-budget", "--allow-test-edit", "--repo-root", str(self.root), "--json",
                "tests/test_skipped.py",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_test_skip.returncode, 1)
        skip_codes = _codes(json.loads(proc_test_skip.stdout)["errors"])
        self.assertIn("DIFF-TEST-SKIP", skip_codes)
        self.assertNotIn("DIFF-UNAUTHORIZED-TEST-EDIT", skip_codes)


class HookInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        self.bin_dir = Path(self.temp.name) / "bin"
        self.bin_dir.mkdir()

    def _run_installer(
        self,
        *args: str,
        with_installed_script_on_path: bool = False,
    ) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env.pop("ANTI_SLOP_BENCHMARK_SUBJECT", None)
        if with_installed_script_on_path:
            stub = self.bin_dir / "anti-slop-hook"
            stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
            env["PATH"] = f"{self.bin_dir}{os.pathsep}{env.get('PATH', '')}"
        else:
            # Strip any directory containing anti-slop-hook from PATH to test fallback cleanly.
            clean_parts = [
                p for p in env.get("PATH", "").split(os.pathsep)
                if p and not (Path(p) / "anti-slop-hook").exists()
            ]
            env["PATH"] = os.pathsep.join(clean_parts)

        return subprocess.run(
            [sys.executable, "-B", str(HOOK_SCRIPT), *args],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_install_dry_run_for_claude_antigravity_and_codex_writes_nothing(self) -> None:
        expected_targets = {
            "claude": self.home / ".claude" / "settings.json",
            "antigravity": self.home / ".gemini" / "config" / "hooks.json",
            "codex": self.home / ".codex" / "hooks.json",
        }
        for cli_name, target_path in expected_targets.items():
            with self.subTest(cli=cli_name):
                proc = self._run_installer("--install", cli_name, "--dry-run")
                self.assertEqual(proc.returncode, 0, msg=proc.stderr)
                self.assertIn("[dry-run]", proc.stdout)
                self.assertIn(str(target_path), proc.stdout)
                self.assertFalse(target_path.exists())
                preview = _extract_json_block(proc.stdout)

                if cli_name == "claude":
                    self.assertIn("PreToolUse", preview["hooks"])
                    self.assertIn("Stop", preview["hooks"])
                    pre_cmd = preview["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
                    stop_cmd = preview["hooks"]["Stop"][0]["hooks"][0]["command"]
                    self.assertIn("--harness claude --stdin-tool-json", pre_cmd)
                    self.assertIn("--harness claude --no-budget", stop_cmd)
                elif cli_name == "antigravity":
                    self.assertNotIn("hooks", preview)
                    block = preview["anti-slop-diff-gate"]
                    self.assertIn("PreToolUse", block)
                    self.assertIsInstance(block["Stop"], list)
                    self.assertNotIn("hooks", block["Stop"][0])
                    self.assertIn("--harness antigravity --stdin-tool-json", block["PreToolUse"][0]["hooks"][0]["command"])
                    self.assertIn("--harness antigravity --no-budget", block["Stop"][0]["command"])
                else:
                    self.assertIn("PreToolUse", preview["hooks"])
                    self.assertIn("PostToolUse", preview["hooks"])
                    self.assertIn("Stop-hook parity", proc.stdout)

    def test_install_backs_up_preserves_existing_deduplicates_and_prefers_console_script(self) -> None:
        # 1. Claude: existing unrelated keys + existing hook + duplicate stale anti-slop entry
        claude_cfg = self.home / ".claude" / "settings.json"
        claude_cfg.parent.mkdir(parents=True, exist_ok=True)
        claude_original = {
            "theme": "dark",
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "echo keep-me"}],
                    },
                    {
                        "matcher": "Edit",
                        "hooks": [{"type": "command", "command": "python3 -B old/run_diff_gate_hook.py --stdin-tool-json"}],
                    },
                    {
                        "matcher": "Write",
                        "hooks": [{"type": "command", "command": "anti-slop-hook --stdin-tool-json"}],
                    },
                ]
            },
        }
        claude_raw = json.dumps(claude_original, indent=2) + "\n"
        claude_cfg.write_text(claude_raw, encoding="utf-8")

        proc1 = self._run_installer("--install", "claude", with_installed_script_on_path=True)
        self.assertEqual(proc1.returncode, 0, msg=proc1.stderr)
        bak_claude = claude_cfg.with_name("settings.json.bak-antislop")
        self.assertTrue(bak_claude.is_file())
        self.assertEqual(bak_claude.read_text(encoding="utf-8"), claude_raw)

        updated_claude = json.loads(claude_cfg.read_text(encoding="utf-8"))
        self.assertEqual(updated_claude["theme"], "dark")
        pre_cmds = [
            h["command"]
            for entry in updated_claude["hooks"]["PreToolUse"]
            for h in entry["hooks"]
        ]
        self.assertIn("echo keep-me", pre_cmds)
        antislop_pre = [c for c in pre_cmds if "anti-slop-hook" in c or "run_diff_gate_hook.py" in c]
        self.assertEqual(antislop_pre, ["anti-slop-hook --harness claude --stdin-tool-json"])

        stop_cmds = [
            h["command"]
            for entry in updated_claude["hooks"]["Stop"]
            for h in entry["hooks"]
        ]
        self.assertEqual(stop_cmds, ["anti-slop-hook --harness claude --no-budget"])

        # Re-running is strictly idempotent with zero duplicates.
        proc2 = self._run_installer("--install", "claude", with_installed_script_on_path=True)
        self.assertEqual(proc2.returncode, 0, msg=proc2.stderr)
        self.assertIn("already up to date", proc2.stdout)
        self.assertEqual(json.loads(claude_cfg.read_text(encoding="utf-8")), updated_claude)

        # 2. Antigravity: preserves other named hooks, backs up to hooks.json.bak-antislop, uses python fallback when console script absent
        agy_cfg = self.home / ".gemini" / "config" / "hooks.json"
        agy_cfg.parent.mkdir(parents=True, exist_ok=True)
        agy_original = {
            "other-custom-hook": {
                "Stop": [{"type": "command", "command": "echo other-hook"}]
            }
        }
        agy_raw = json.dumps(agy_original, indent=2) + "\n"
        agy_cfg.write_text(agy_raw, encoding="utf-8")

        proc_agy = self._run_installer("--install", "antigravity", with_installed_script_on_path=False)
        self.assertEqual(proc_agy.returncode, 0, msg=proc_agy.stderr)
        bak_agy = agy_cfg.with_name("hooks.json.bak-antislop")
        self.assertTrue(bak_agy.is_file())
        self.assertEqual(bak_agy.read_text(encoding="utf-8"), agy_raw)

        updated_agy = json.loads(agy_cfg.read_text(encoding="utf-8"))
        self.assertIn("other-custom-hook", updated_agy)
        self.assertIn("anti-slop-diff-gate", updated_agy)
        agy_stop_cmd = updated_agy["anti-slop-diff-gate"]["Stop"][0]["command"]
        self.assertIn("python3 -B", agy_stop_cmd)
        self.assertIn("run_diff_gate_hook.py", agy_stop_cmd)
        self.assertIn("--harness antigravity --no-budget", agy_stop_cmd)

        # Second Antigravity install is idempotent.
        proc_agy_2 = self._run_installer("--install", "antigravity", with_installed_script_on_path=False)
        self.assertEqual(proc_agy_2.returncode, 0, msg=proc_agy_2.stderr)
        self.assertIn("already up to date", proc_agy_2.stdout)

        # 3. Codex: creates ~/.codex/hooks.json cleanly, idempotent on second run.
        codex_cfg = self.home / ".codex" / "hooks.json"
        proc_codex = self._run_installer("--install", "codex", with_installed_script_on_path=True)
        self.assertEqual(proc_codex.returncode, 0, msg=proc_codex.stderr)
        self.assertTrue(codex_cfg.is_file())
        self.assertFalse(codex_cfg.with_name("hooks.json.bak-antislop").exists())
        codex_data = json.loads(codex_cfg.read_text(encoding="utf-8"))
        self.assertEqual(
            codex_data["hooks"]["PreToolUse"][0]["hooks"][0]["command"],
            "anti-slop-hook --harness codex --stdin-tool-json",
        )
        self.assertEqual(
            codex_data["hooks"]["PostToolUse"][0]["hooks"][0]["command"],
            "anti-slop-hook --harness codex --no-budget",
        )

    def test_install_refuses_to_overwrite_malformed_json(self) -> None:
        claude_cfg = self.home / ".claude" / "settings.json"
        claude_cfg.parent.mkdir(parents=True, exist_ok=True)
        broken = "{ not valid json"
        claude_cfg.write_text(broken, encoding="utf-8")

        proc = self._run_installer("--install", "claude")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Failed to parse existing config", proc.stderr)
        self.assertEqual(claude_cfg.read_text(encoding="utf-8"), broken)

    def test_install_ignores_ephemeral_uvx_archive_v0_path_and_uses_uvx_fallback(self) -> None:
        # 1. Ephemeral uv archive-v0 bin on PATH must NEVER be treated as a permanent binary.
        ephemeral_root = Path(self.temp.name) / "uv_cache" / "archive-v0" / "deadbeef"
        ephemeral_bin = ephemeral_root / "bin"
        ephemeral_bin.mkdir(parents=True, exist_ok=True)
        ephemeral_stub = ephemeral_bin / "anti-slop-hook"
        ephemeral_stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        ephemeral_stub.chmod(ephemeral_stub.stat().st_mode | stat.S_IXUSR)

        base_env = os.environ.copy()
        base_env["HOME"] = str(self.home)
        base_env.pop("ANTI_SLOP_BENCHMARK_SUBJECT", None)
        clean_parts = [
            p for p in base_env.get("PATH", "").split(os.pathsep)
            if p and not (Path(p) / "anti-slop-hook").exists()
        ]
        base_env["PATH"] = f"{ephemeral_bin}{os.pathsep}{os.pathsep.join(clean_parts)}"

        # Running from persistent local checkout with only archive-v0/bin/anti-slop-hook on PATH:
        # must ignore archive-v0 bin and wire persistent `python3 -B <script>`, NOT bare `anti-slop-hook`.
        proc_local = subprocess.run(
            [sys.executable, "-B", str(HOOK_SCRIPT), "--install", "claude", "--dry-run"],
            capture_output=True,
            text=True,
            env=base_env,
            check=False,
        )
        self.assertEqual(proc_local.returncode, 0, msg=proc_local.stderr)
        preview_local = _extract_json_block(proc_local.stdout)
        local_cmd = preview_local["hooks"]["Stop"][0]["hooks"][0]["command"]
        self.assertTrue(local_cmd.startswith("python3 -B "), msg=local_cmd)
        self.assertNotIn("archive-v0", local_cmd)

        # 2. Running the script itself from inside an ephemeral uvx archive-v0 dir:
        # must wire `uvx --from git+https://github.com/jremick/anti-slop anti-slop-hook` (never a dead cache path).
        ephemeral_script = ephemeral_root / "gates" / "hooks" / "run_diff_gate_hook.py"
        ephemeral_script.parent.mkdir(parents=True, exist_ok=True)
        ephemeral_script.write_text(HOOK_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")

        proc_uvx = subprocess.run(
            [sys.executable, "-B", str(ephemeral_script), "--install", "claude", "--dry-run"],
            capture_output=True,
            text=True,
            env=base_env,
            check=False,
        )
        self.assertEqual(proc_uvx.returncode, 0, msg=proc_uvx.stderr)
        preview_uvx = _extract_json_block(proc_uvx.stdout)
        uvx_stop_cmd = preview_uvx["hooks"]["Stop"][0]["hooks"][0]["command"]
        self.assertEqual(
            uvx_stop_cmd,
            "uvx --from git+https://github.com/jremick/anti-slop anti-slop-hook --harness claude --no-budget",
        )
        self.assertNotIn("archive-v0", uvx_stop_cmd)
        self.assertIn("uv tool install", proc_uvx.stdout)


if __name__ == "__main__":
    unittest.main()
