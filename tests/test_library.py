"""Stdlib-only tests for the curated optional rule library (library/catalog.json & library/README.md)."""

from __future__ import annotations

import copy
import importlib.resources
import json
from pathlib import Path
import re
import sys
import unittest

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 (e.g., macOS system python3 3.9)
    tomllib = None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gates import diff_check  # noqa: E402
from gates import learn  # noqa: E402


class OptionalRuleLibraryTests(unittest.TestCase):
    def test_catalog_validates_and_has_expected_packs_and_exclusions(self) -> None:
        summary = learn.validate_library_catalog()
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["packs"], 6)
        self.assertEqual(summary["rules"], 10)
        self.assertEqual(summary["deterministic_rules"], 7)
        self.assertEqual(summary["prompt_rules"], 3)
        self.assertEqual(summary["excluded"], 6)

        catalog = learn.load_library_catalog()
        pack_ids = [p["id"] for p in catalog["optional_packs"]]
        self.assertEqual(
            pack_ids,
            [
                "network-timeouts",
                "security-boundaries",
                "comment-hygiene",
                "verification-proof",
                "build-config-hygiene",
                "architecture-simplicity",
            ],
        )

        # Verify default_core covers Layer A, Layer B (all 11 STRUCT-* + ARCH-* checks), and R1-R7.
        dc = catalog["default_core"]
        layer_b_codes = {item["code"] for item in dc["layer_b_structural_checks"]}
        self.assertEqual(len(layer_b_codes), 11)
        for required_code in (
            "STRUCT-COMMENTED-CODE",
            "ARCH-CIRCULAR-IMPORT",
            "ARCH-SINGLE-IMPL-WRAPPER",
            "ARCH-BOUNDARY-SCATTER",
        ):
            self.assertIn(required_code, layer_b_codes)
        core_rule_ids = [item["id"] for item in dc["standing_core_rules"]["rules"]]
        self.assertEqual(core_rule_ids, ["R1", "R2", "R3", "R4", "R5", "R6", "R7"])

    def test_every_deterministic_rule_precision_on_extended_bad_and_valid_cases(self) -> None:
        catalog = learn.load_library_catalog()
        rules_by_id = {
            r["id"]: r
            for pack in catalog["optional_packs"]
            for r in pack["rules"]
        }

        extra_cases = {
            "OPT-NET-01": (
                [
                    'resp = requests.post("https://example.com/hook", json=payload)\n',
                    'raw = urllib.request.urlopen("https://example.com/status")\n',
                ],
                [
                    'resp = requests.get("https://example.com/health", timeout=(3, 10))\n',
                    'resp = requests.get(\n    "https://example.com/health",\n    timeout=10,\n)\n',
                    'raw = urllib.request.urlopen(req, timeout=5)\n',
                ],
            ),
            "OPT-NET-02": (
                [
                    'const r = await fetch("https://example.com/items", { method: "POST" });\n',
                ],
                [
                    'const r = await fetch(url, { method: "POST", signal: controller.signal });\n',
                    'const r = client.fetch("cached-key");\n',
                ],
            ),
            "OPT-SEC-01": (
                [
                    'subprocess.Popen("ls -la", shell=True)\n',
                    'subprocess.check_output(cmd, shell=True)\n',
                ],
                [
                    'subprocess.run(["ls", "-la"], check=True)\n',
                    'subprocess.run(["ls"], shell=False)\n',
                ],
            ),
            "OPT-SEC-02": (
                [
                    'data = yaml.load(stream, Loader=yaml.FullLoader)\n',
                ],
                [
                    'data = yaml.safe_load(stream)\n',
                    'data = yaml.load(stream, Loader=yaml.CSafeLoader)\n',
                ],
            ),
            "OPT-SEC-03": (
                [
                    'exec(generated_source)\n',
                ],
                [
                    'model.eval()\n',
                    'cursor.execute("SELECT 1")\n',
                    'ast.literal_eval(raw)\n',
                ],
            ),
            "OPT-CFG-01": (
                [
                    'FROM --platform=linux/amd64 node:latest AS build\n',
                ],
                [
                    'FROM python:3.12-slim@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n',
                ],
            ),
            "OPT-CFG-02": (
                [
                    'os.chmod(upload_dir, 0o777)\n',
                    'chmod 0777 ./run.sh\n',
                ],
                [
                    'os.chmod(upload_dir, 0o750)\n',
                    'chmod 644 config.json\n',
                ],
            ),
        }

        for rule_id, (bad_samples, valid_samples) in extra_cases.items():
            rule = rules_by_id[rule_id]
            compiled = re.compile(rule["pattern"])
            mode = rule.get("match_mode", "line")
            for bad in bad_samples:
                with self.subTest(rule=rule_id, kind="bad", sample=bad.strip()):
                    hits = learn._find_pattern_hits_in_text(bad, compiled, mode)
                    self.assertTrue(hits, msg=f"{rule_id} missed bad sample: {bad!r}")
            for good in valid_samples:
                with self.subTest(rule=rule_id, kind="valid", sample=good.strip()):
                    hits = learn._find_pattern_hits_in_text(good, compiled, mode)
                    self.assertEqual(hits, [], msg=f"{rule_id} falsely flagged valid sample: {good!r}")

    def test_validate_library_catalog_rejects_broken_entries(self) -> None:
        base = learn.load_library_catalog()

        # 1. Duplicate OPT-* rule ID fails.
        dup = copy.deepcopy(base)
        dup["optional_packs"][1]["rules"][0]["id"] = dup["optional_packs"][0]["rules"][0]["id"]
        with self.assertRaisesRegex(learn.LearnError, "Duplicate optional rule id"):
            learn.validate_library_catalog(dup)

        # 2. Prompt rule exceeding 45 words fails.
        long_prompt = copy.deepcopy(base)
        long_prompt["optional_packs"][2]["rules"][0]["rule_text"] = " ".join(["word"] * 50)
        with self.assertRaisesRegex(learn.LearnError, "max 45"):
            learn.validate_library_catalog(long_prompt)

        # 3. Prompt rule missing why_not_deterministic fails.
        no_why = copy.deepcopy(base)
        no_why["optional_packs"][2]["rules"][0]["why_not_deterministic"] = ""
        with self.assertRaisesRegex(learn.LearnError, "why_not_deterministic"):
            learn.validate_library_catalog(no_why)

        # 4. Deterministic rule failing to catch bad_example fails.
        bad_miss = copy.deepcopy(base)
        bad_miss["optional_packs"][0]["rules"][0]["bad_example"] = "x = 1\n"
        with self.assertRaisesRegex(learn.LearnError, "failed to catch its own bad_example"):
            learn.validate_library_catalog(bad_miss)

        # 5. Deterministic rule falsely matching valid_neighbouring_case fails.
        valid_fp = copy.deepcopy(base)
        valid_fp["optional_packs"][0]["rules"][0]["valid_neighbouring_case"] = (
            valid_fp["optional_packs"][0]["rules"][0]["bad_example"] + "# extra\n"
        )
        with self.assertRaisesRegex(learn.LearnError, "falsely matched its own valid_neighbouring_case"):
            learn.validate_library_catalog(valid_fp)

    def test_library_readme_and_package_data_hygiene(self) -> None:
        readme_path = REPO_ROOT / "library" / "README.md"
        self.assertTrue(readme_path.is_file())
        readme_text = readme_path.read_text(encoding="utf-8")
        self.assertNotIn("\u2014", readme_text)
        res = diff_check.check_files(
            ["library/README.md"],
            repo_root=REPO_ROOT,
            strict_prose=True,
        )
        self.assertTrue(res["ok"], msg=res["errors"])
        self.assertEqual(res["warnings"], [], msg=res["warnings"])

        # Packaged resource lookup via importlib.resources works cleanly.
        packaged = json.loads(
            importlib.resources.files("library").joinpath("catalog.json").read_text(encoding="utf-8")
        )
        self.assertEqual(packaged["schema_version"], 1)

        # pyproject.toml bundles library package + catalog.json.
        pyproject_raw = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        if tomllib is not None:
            parsed = tomllib.loads(pyproject_raw)
            setuptools_cfg = parsed.get("tool", {}).get("setuptools", {})
            self.assertIn("library", setuptools_cfg.get("packages", []))
            self.assertIn("catalog.json", setuptools_cfg.get("package-data", {}).get("library", []))
        else:
            self.assertIn('"library"', pyproject_raw)
            self.assertIn('library = ["catalog.json"]', pyproject_raw)


if __name__ == "__main__":
    unittest.main()
