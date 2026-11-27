"""Stdlib-only tests for the unified `anti-slop` CLI (`gates/cli.py`) and bundled agent skill."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_SCRIPT = REPO_ROOT / "gates/cli.py"
SKILL_FILE = REPO_ROOT / "skills/anti-slop/SKILL.md"
SKILLS_README = REPO_ROOT / "skills/README.md"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class UnifiedCliAndSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()

    def _run_cli(
        self,
        *args: str,
        stdin_text: str = "",
        env_extra: dict | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env.pop("ANTI_SLOP_BENCHMARK_SUBJECT", None)
        env.pop("ANTI_SLOP_ALLOW_TEST_EDIT", None)
        env.pop("ANTI_SLOP_TELEMETRY", None)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, "-B", str(CLI_SCRIPT), *args],
            input=stdin_text,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            check=False,
        )

    def test_version_help_and_unknown_subcommand(self) -> None:
        cli_mod = importlib.import_module("gates.cli")
        expected_ver = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()

        for flag in ("--version", "-V"):
            with self.subTest(flag=flag):
                proc = self._run_cli(flag)
                self.assertEqual(proc.returncode, 0, msg=proc.stderr)
                self.assertEqual(proc.stdout.strip(), f"anti-slop {expected_ver}")

        # Direct version-file lookup and fallback to "0.7.0".
        custom_ver = self.tmp / "VERSION"
        custom_ver.write_text("0.7.0\n", encoding="utf-8")
        self.assertEqual(cli_mod.get_version(version_file=custom_ver), "0.7.0")
        self.assertEqual(cli_mod.get_version(version_file=self.tmp / "MISSING_VERSION"), "0.7.0")

        proc_help = self._run_cli("--help")
        self.assertEqual(proc_help.returncode, 0, msg=proc_help.stderr)
        for sub in ("review", "audit", "diff", "learn", "mutate", "verify", "hook", "api", "skill"):
            self.assertIn(sub, proc_help.stdout)

        proc_bad = self._run_cli("does-not-exist")
        self.assertEqual(proc_bad.returncode, 2)
        self.assertIn("unknown subcommand", proc_bad.stderr)

    def test_subcommand_dispatch_across_all_six_gate_tools(self) -> None:
        # Prepare a small self-contained sample project for real end-to-end subcommand dispatch.
        proj = self.tmp / "sample_repo"
        (proj / "src").mkdir(parents=True)
        (proj / "tests").mkdir(parents=True)
        (proj / "src" / "clean.py").write_text(
            "def add(a: int, b: int) -> int:\n    return a + b\n",
            encoding="utf-8",
        )
        (proj / "src" / "dirty.py").write_text(
            "def run() -> None:\n    breakpoint()\n",
            encoding="utf-8",
        )
        (proj / "tests" / "test_clean.py").write_text(
            "import unittest\n"
            "from src.clean import add\n\n"
            "class TestAdd(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        self.assertEqual(add(2, 3), 5)\n"
            "        self.assertEqual(add(-1, 4), 3)\n",
            encoding="utf-8",
        )
        api_ok_cfg = self.tmp / "api_ok.json"
        api_ok_cfg.write_text(
            json.dumps({"model": "gpt-6.2-astra", "reasoning": {"effort": "medium"}}),
            encoding="utf-8",
        )
        api_bad_cfg = self.tmp / "api_bad.json"
        api_bad_cfg.write_text(
            json.dumps({"model": "gpt-6.2-astra", "reasoning": {"effort": "none"}}),
            encoding="utf-8",
        )

        # 1. review
        proc_rev = self._run_cli("review", "--repo-root", str(proj), "--json", "src/dirty.py")
        self.assertEqual(proc_rev.returncode, 1, msg=proc_rev.stdout + proc_rev.stderr)
        rev_data = json.loads(proc_rev.stdout)
        self.assertFalse(rev_data["ok"])
        self.assertIn("DIFF-DEBUG-LEFTOVER", {e["code"] for e in rev_data["errors"]})

        # 2. diff
        proc_diff = self._run_cli("diff", "--repo-root", str(proj), "--no-budget", "--json", "src/clean.py")
        self.assertEqual(proc_diff.returncode, 0, msg=proc_diff.stdout + proc_diff.stderr)
        self.assertTrue(json.loads(proc_diff.stdout)["ok"])

        # 3. learn
        proc_learn = self._run_cli("learn", "library", "list", "--json")
        self.assertEqual(proc_learn.returncode, 0, msg=proc_learn.stderr)
        learn_data = json.loads(proc_learn.stdout)
        self.assertGreater(len(learn_data["optional_packs"]), 0)

        # 4. mutate
        test_cmd = f"{sys.executable} -B -m unittest discover -s tests"
        proc_mut = self._run_cli(
            "mutate",
            "--repo-root", str(proj),
            "--files", "src/clean.py",
            "--test-cmd", test_cmd,
            "--json",
        )
        self.assertEqual(proc_mut.returncode, 0, msg=proc_mut.stdout + proc_mut.stderr)
        mut_data = json.loads(proc_mut.stdout)
        self.assertTrue(mut_data["ok"])
        self.assertGreater(mut_data["summary"]["killed"], 0)

        # 5. hook
        hook_payload = json.dumps({
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "tests/test_clean.py"},
        })
        proc_hook = self._run_cli(
            "hook",
            "--repo-root", str(proj),
            "--stdin-tool-json",
            stdin_text=hook_payload,
        )
        self.assertEqual(proc_hook.returncode, 2, msg=proc_hook.stderr)
        self.assertIn("DIFF-UNAUTHORIZED-TEST-EDIT", proc_hook.stderr)

        # 6. api
        proc_api_ok = self._run_cli("api", "--json", str(api_ok_cfg))
        self.assertEqual(proc_api_ok.returncode, 0, msg=proc_api_ok.stdout + proc_api_ok.stderr)
        self.assertTrue(json.loads(proc_api_ok.stdout)["ok"])

        proc_api_bad = self._run_cli("api", "--json", str(api_bad_cfg))
        self.assertEqual(proc_api_bad.returncode, 1, msg=proc_api_bad.stdout + proc_api_bad.stderr)
        self.assertIn("GPT-EFFORT-NONE", {e["code"] for e in json.loads(proc_api_bad.stdout)["errors"]})

        # 7. verify (--help dispatch and live ad-hoc CLI check)
        proc_ver_help = self._run_cli("verify", "--help")
        self.assertEqual(proc_ver_help.returncode, 0, msg=proc_ver_help.stderr)
        self.assertIn("--check-receipt", proc_ver_help.stdout)

        proc_ver_live = self._run_cli(
            "verify",
            "--repo-root", str(proj),
            "--cmd", f"{sys.executable} -B -c \"print('verify-ok')\"",
            "--expect-stdout", "verify-ok",
            "--no-receipt",
            "--json",
        )
        self.assertEqual(proc_ver_live.returncode, 0, msg=proc_ver_live.stdout + proc_ver_live.stderr)
        self.assertTrue(json.loads(proc_ver_live.stdout)["ok"])

    def test_skill_show_matches_source_meets_budget_and_passes_strict_prose(self) -> None:
        proc = self._run_cli("skill", "show")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)

        expected_text = SKILL_FILE.read_text(encoding="utf-8")
        self.assertEqual(proc.stdout, expected_text)

        # Frontmatter, compactness (<= 120 lines), zero em-dashes, and all 4 workflows.
        lines = expected_text.splitlines()
        self.assertLessEqual(len(lines), 120)
        self.assertEqual(lines[0], "---")
        self.assertIn("name: anti-slop", expected_text)
        self.assertIn("description:", expected_text)
        self.assertNotIn("\u2014", expected_text)
        self.assertNotIn("\u2014", SKILLS_README.read_text(encoding="utf-8"))
        for required_phrase in (
            "anti-slop review --json",
            "ARCH-*",
            "anti-slop mutate",
            "JS/TS",
            "anti-slop verify",
            "--check-receipt",
            "anti-slop learn library list",
            "anti-slop learn verify",
            "approve",
            "anti-slop learn mine --json",
            "Tier 1",
            "Tier 2",
            "Tier 3",
        ):
            self.assertIn(required_phrase, expected_text)

        diff_check = importlib.import_module("gates.diff_check")
        res = diff_check.check_files(
            ["skills/anti-slop/SKILL.md", "skills/README.md"],
            repo_root=REPO_ROOT,
            strict_prose=True,
        )
        self.assertTrue(res["ok"], msg=res["errors"])
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["warnings"], [])

    def test_skill_install_dry_run_default_paths_backup_and_idempotency(self) -> None:
        bundled_text = SKILL_FILE.read_text(encoding="utf-8")

        # 1. Default per-harness paths with --dry-run write nothing.
        expected_targets = {
            "claude": self.home / ".claude" / "skills" / "anti-slop" / "SKILL.md",
            "antigravity": self.home / ".gemini" / "config" / "skills" / "anti-slop" / "SKILL.md",
            "codex": self.home / ".codex" / "skills" / "anti-slop" / "SKILL.md",
        }
        for target, dest_path in expected_targets.items():
            with self.subTest(target=target, mode="dry-run"):
                proc = self._run_cli("skill", "install", target, "--dry-run")
                self.assertEqual(proc.returncode, 0, msg=proc.stderr)
                self.assertIn("[dry-run]", proc.stdout)
                self.assertIn(str(dest_path), proc.stdout)
                self.assertFalse(dest_path.exists())

        # 2. Real install to default claude path + idempotency.
        claude_dest = expected_targets["claude"]
        proc_install = self._run_cli("skill", "install", "claude")
        self.assertEqual(proc_install.returncode, 0, msg=proc_install.stderr)
        self.assertTrue(claude_dest.is_file())
        self.assertEqual(claude_dest.read_text(encoding="utf-8"), bundled_text)
        self.assertFalse(claude_dest.with_name("SKILL.md.bak-antislop").exists())

        proc_idem = self._run_cli("skill", "install", "claude")
        self.assertEqual(proc_idem.returncode, 0, msg=proc_idem.stderr)
        self.assertIn("already up to date", proc_idem.stdout)
        self.assertFalse(claude_dest.with_name("SKILL.md.bak-antislop").exists())

        # 3. Custom --dest directory override with backup on differing existing file.
        custom_dir = self.tmp / "custom_skill_dest"
        custom_file = custom_dir / "SKILL.md"
        custom_dir.mkdir(parents=True)
        prior_text = "---\nname: anti-slop\n---\n# Old custom version\n"
        custom_file.write_text(prior_text, encoding="utf-8")

        # --dry-run previews backup without modifying disk.
        proc_dry_upd = self._run_cli(
            "skill", "install", "codex", "--dest", str(custom_dir), "--dry-run"
        )
        self.assertEqual(proc_dry_upd.returncode, 0, msg=proc_dry_upd.stderr)
        self.assertIn("[dry-run]", proc_dry_upd.stdout)
        self.assertIn("SKILL.md.bak-antislop", proc_dry_upd.stdout)
        self.assertEqual(custom_file.read_text(encoding="utf-8"), prior_text)
        self.assertFalse(custom_file.with_name("SKILL.md.bak-antislop").exists())

        # Real install backs up prior version to SKILL.md.bak-antislop and writes bundled skill.
        proc_upd = self._run_cli("skill", "install", "codex", "--dest", str(custom_dir))
        self.assertEqual(proc_upd.returncode, 0, msg=proc_upd.stderr)
        bak_file = custom_file.with_name("SKILL.md.bak-antislop")
        self.assertTrue(bak_file.is_file())
        self.assertEqual(bak_file.read_text(encoding="utf-8"), prior_text)
        self.assertEqual(custom_file.read_text(encoding="utf-8"), bundled_text)

        # Re-running with explicit .md file path is idempotent.
        proc_direct_idem = self._run_cli(
            "skill", "install", "antigravity", "--dest", str(custom_file)
        )
        self.assertEqual(proc_direct_idem.returncode, 0, msg=proc_direct_idem.stderr)
        self.assertIn("already up to date", proc_direct_idem.stdout)


if __name__ == "__main__":
    unittest.main()
