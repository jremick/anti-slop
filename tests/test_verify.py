"""Stdlib-only tests for live E2E & real-artifact verification (`gates/verify.py`)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gates import verify  # noqa: E402


VERIFY_SCRIPT = REPO_ROOT / "gates/verify.py"


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=root, check=True)


def _write_test_http_server(dest: Path) -> None:
    """Write a real stdlib HTTP server fixture supporting health, JSON, POST, and optional SIGTERM trap."""
    dest.write_text(
        "import json\n"
        "import os\n"
        "import signal\n"
        "import subprocess\n"
        "import sys\n"
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n\n"
        "PORT = int(sys.argv[1])\n"
        "PID_FILE = sys.argv[2]\n"
        "IGNORE_TERM = '--ignore-term' in sys.argv\n"
        "SPAWN_CHILD = '--spawn-child' in sys.argv\n\n"
        "if IGNORE_TERM:\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n\n"
        "child_pid = None\n"
        "if SPAWN_CHILD:\n"
        "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "    child_pid = child.pid\n\n"
        "with open(PID_FILE, 'w', encoding='utf-8') as fh:\n"
        "    json.dump({'pid': os.getpid(), 'pgid': os.getpgid(0), 'child_pid': child_pid}, fh)\n\n"
        "class Handler(BaseHTTPRequestHandler):\n"
        "    def log_message(self, fmt, *args):\n"
        "        pass\n"
        "    def _send(self, code, payload, ctype='application/json'):\n"
        "        raw = payload.encode('utf-8')\n"
        "        self.send_response(code)\n"
        "        self.send_header('Content-Type', ctype)\n"
        "        self.send_header('Content-Length', str(len(raw)))\n"
        "        self.end_headers()\n"
        "        self.wfile.write(raw)\n"
        "    def do_GET(self):\n"
        "        if self.path == '/health':\n"
        "            body = json.dumps({'status': 'ok', 'service': 'demo', 'meta': {'version': 2, 'ready': True}})\n"
        "            self._send(200, body)\n"
        "        elif self.path == '/error':\n"
        "            self._send(500, 'internal failure marker', 'text/plain')\n"
        "        else:\n"
        "            self._send(404, json.dumps({'error': 'not_found'}))\n"
        "    def do_POST(self):\n"
        "        length = int(self.headers.get('Content-Length', '0'))\n"
        "        raw = self.rfile.read(length).decode('utf-8') if length else '{}'\n"
        "        data = json.loads(raw)\n"
        "        resp = {'created': True, 'item': data, 'header': self.headers.get('X-Test-Header')}\n"
        "        self._send(201, json.dumps(resp))\n\n"
        "server = HTTPServer(('127.0.0.1', PORT), Handler)\n"
        "print(f'READY_ON_PORT:{PORT}', flush=True)\n"
        "server.serve_forever()\n",
        encoding="utf-8",
    )


class VerifyUnitTests(unittest.TestCase):
    def test_json_subset_match_recursive_and_strict_bool(self) -> None:
        actual = {
            "status": "ok",
            "count": 3,
            "active": True,
            "nested": {"a": 1, "b": "two", "extra": [10, 20]},
            "items": [{"id": 1, "name": "alpha", "unused": True}],
        }
        self.assertIsNone(verify.json_subset_match({"status": "ok", "nested": {"a": 1}}, actual))
        self.assertIsNone(verify.json_subset_match({"items": [{"id": 1}]}, actual))

        # Missing key, wrong scalar, and strict bool-vs-int mismatch.
        self.assertIn("missing expected key", verify.json_subset_match({"nested": {"missing": 1}}, actual) or "")
        self.assertIn("expected 'bad'", verify.json_subset_match({"status": "bad"}, actual) or "")
        self.assertIsNotNone(verify.json_subset_match({"active": 1}, actual))
        self.assertIsNotNone(verify.json_subset_match({"count": True}, actual))
        self.assertIn("length", verify.json_subset_match({"items": []}, actual) or "")

    def test_example_recipe_validates_cleanly(self) -> None:
        recipe = verify.example_recipe()
        validated = verify.validate_recipe(recipe)
        self.assertEqual(len(validated["services"]), 1)
        self.assertEqual(len(validated["checks"]), 3)
        self.assertEqual({c["kind"] for c in validated["checks"]}, {"http", "cli", "file"})

    def test_validate_recipe_rejects_invalid_configs(self) -> None:
        bad_cases = [
            [],
            {"checks": []},
            {"checks": [{"id": "c1", "kind": "unknown"}]},
            {"checks": [{"id": "c1", "kind": "http", "url": "ftp://example.com"}]},
            {"checks": [{"id": "c1", "kind": "http", "url": "http://127.0.0.1:80/", "body": "a", "json_body": {}}]},
            {"checks": [{"id": "c1", "kind": "cli", "command": "", "expect_exit": 0}]},
            {"checks": [{"id": "dup", "kind": "file", "path": "a.txt"}, {"id": "dup", "kind": "file", "path": "b.txt"}]},
            {"services": [{"name": "s", "command": "echo hi", "ready_port": 99999}], "checks": [{"id": "f", "kind": "file", "path": "a"}]},
        ]
        for bad in bad_cases:
            with self.subTest(bad=bad):
                with self.assertRaises(verify.VerifyConfigError):
                    verify.validate_recipe(bad)


class VerifyLiveIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.server_script = self.root / "demo_server.py"
        _write_test_http_server(self.server_script)
        (self.root / "app.py").write_text("print('app-v1')\n", encoding="utf-8")
        (self.root / "artifact.txt").write_text("build ok: release-ready\n", encoding="utf-8")
        _init_git_repo(self.root)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=self.root, check=True)

    def _run_verify(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-B", str(VERIFY_SCRIPT), "--repo-root", str(self.root), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_recipe_mode_live_http_cli_file_and_clean_pgid_teardown(self) -> None:
        port = _pick_free_port()
        pid_file = self.root / "server_pid.json"
        recipe_path = self.root / ".anti-slop/verify.json"
        recipe_path.parent.mkdir(parents=True, exist_ok=True)
        recipe = {
            "services": [
                {
                    "name": "demo-api",
                    "command": [
                        sys.executable, "-B", "demo_server.py",
                        str(port), "server_pid.json", "--spawn-child",
                    ],
                    "ready_url": f"http://127.0.0.1:{port}/health",
                    "ready_stdout": f"READY_ON_PORT:{port}",
                    "ready_timeout_s": 10,
                }
            ],
            "checks": [
                {
                    "id": "health-get",
                    "kind": "http",
                    "url": f"http://127.0.0.1:{port}/health",
                    "expect_status": 200,
                    "expect_json": {"status": "ok", "meta": {"version": 2, "ready": True}},
                    "expect_body_contains": ["demo"],
                    "expect_body_not_contains": ["error"],
                },
                {
                    "id": "create-post",
                    "kind": "http",
                    "url": f"http://127.0.0.1:{port}/items",
                    "method": "POST",
                    "headers": {"X-Test-Header": "hdr-42"},
                    "json_body": {"title": "widget"},
                    "expect_status": 201,
                    "expect_json": {"created": True, "item": {"title": "widget"}, "header": "hdr-42"},
                },
                {
                    "id": "app-cli",
                    "kind": "cli",
                    "command": [sys.executable, "-B", "app.py"],
                    "expect_exit": 0,
                    "expect_stdout_contains": ["app-v1"],
                    "expect_stdout_not_contains": ["error"],
                    "expect_stderr_not_contains": ["Traceback"],
                },
                {
                    "id": "artifact-file",
                    "kind": "file",
                    "path": "artifact.txt",
                    "must_exist": True,
                    "non_empty": True,
                    "contains": ["release-ready"],
                },
            ],
        }
        recipe_path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")

        proc = self._run_verify("--json")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["tier"], "tier1_live_e2e")
        self.assertEqual(report["summary"]["total"], 4)
        self.assertEqual(report["summary"]["passed"], 4)
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertTrue(report["services"][0]["ready"])
        self.assertTrue(report["services"][0]["clean_teardown"])

        # Verify BOTH the server process and its spawned child in the PGID are completely dead!
        pid_info = json.loads(pid_file.read_text(encoding="utf-8"))
        self.assertFalse(_pid_alive(pid_info["pid"]), msg="Server process leaked after verify exit")
        self.assertFalse(_pid_alive(pid_info["child_pid"]), msg="Child process in service PGID leaked after verify exit")

        # Verify receipt exists, has valid digest, and contains ZERO workstation paths.
        receipt_file = self.root / ".anti-slop/last-verify.json"
        self.assertTrue(receipt_file.is_file())
        raw_receipt = receipt_file.read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), raw_receipt)
        self.assertNotIn(str(self.root.resolve()), raw_receipt)
        self.assertNotIn(str(Path.home()), raw_receipt)

        # Fresh receipt passes --check-receipt.
        chk_ok = self._run_verify("--check-receipt", "--json")
        self.assertEqual(chk_ok.returncode, 0, msg=chk_ok.stdout + chk_ok.stderr)
        self.assertTrue(json.loads(chk_ok.stdout)["ok"])

    def test_stubborn_sigterm_ignoring_service_is_force_killed_by_pgid(self) -> None:
        port = _pick_free_port()
        pid_file = self.root / "stubborn_pid.json"
        recipe = {
            "services": [
                {
                    "name": "stubborn",
                    "command": [
                        sys.executable, "-B", "demo_server.py",
                        str(port), "stubborn_pid.json", "--ignore-term", "--spawn-child",
                    ],
                    "ready_port": port,
                    "ready_timeout_s": 10,
                }
            ],
            "checks": [
                {
                    "id": "ping",
                    "kind": "http",
                    "url": f"http://127.0.0.1:{port}/health",
                    "expect_status": 200,
                }
            ],
        }
        report = verify.run_verification(recipe, repo_root=self.root, write_receipt=False)
        self.assertTrue(report["ok"])
        self.assertTrue(report["services"][0]["clean_teardown"])
        pid_info = json.loads(pid_file.read_text(encoding="utf-8"))
        self.assertFalse(_pid_alive(pid_info["pid"]))
        self.assertFalse(_pid_alive(pid_info["child_pid"]))

    def test_service_startup_failure_tears_down_earlier_services_and_exits_2(self) -> None:
        port = _pick_free_port()
        pid_file = self.root / "first_pid.json"
        recipe_path = self.root / "bad_start.json"
        recipe = {
            "services": [
                {
                    "name": "first-ok",
                    "command": [sys.executable, "-B", "demo_server.py", str(port), "first_pid.json"],
                    "ready_port": port,
                    "ready_timeout_s": 10,
                },
                {
                    "name": "second-crash",
                    "command": [sys.executable, "-c", "import sys; print('boom'); sys.exit(3)"],
                    "ready_stdout": "NEVER_PRINTED",
                    "ready_timeout_s": 5,
                },
            ],
            "checks": [
                {"id": "never-runs", "kind": "file", "path": "artifact.txt"},
            ],
        }
        recipe_path.write_text(json.dumps(recipe), encoding="utf-8")

        proc = self._run_verify("--recipe", str(recipe_path), "--no-receipt", "--json")
        self.assertEqual(proc.returncode, 2, msg=proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertFalse(data["ok"])
        self.assertIn("second-crash", data["error"])
        pid_info = json.loads(pid_file.read_text(encoding="utf-8"))
        self.assertFalse(_pid_alive(pid_info["pid"]), msg="Earlier started service leaked on second service startup failure")

    def test_adhoc_cmd_and_start_http_get_modes(self) -> None:
        # 1. Passing --cmd
        proc_cmd_ok = self._run_verify(
            "--cmd", f"{sys.executable} -B app.py",
            "--expect-exit", "0",
            "--expect-stdout", "app-v1",
            "--no-receipt",
            "--json",
        )
        self.assertEqual(proc_cmd_ok.returncode, 0, msg=proc_cmd_ok.stdout + proc_cmd_ok.stderr)
        self.assertTrue(json.loads(proc_cmd_ok.stdout)["ok"])

        # 2. Failing --cmd (wrong exit code)
        proc_cmd_fail = self._run_verify(
            "--cmd", f"{sys.executable} -c \"import sys; sys.exit(4)\"",
            "--expect-exit", "0",
            "--no-receipt",
            "--json",
        )
        self.assertEqual(proc_cmd_fail.returncode, 1)
        data_fail = json.loads(proc_cmd_fail.stdout)
        self.assertFalse(data_fail["ok"])
        self.assertEqual(data_fail["checks"][0]["exit_code"], 4)

        # 3. Ad-hoc --start + --ready-url + --http-get + --expect-contains
        port = _pick_free_port()
        pid_file = self.root / "adhoc_pid.json"
        start_cmd = f"{sys.executable} -B demo_server.py {port} adhoc_pid.json"
        proc_http = self._run_verify(
            "--start", start_cmd,
            "--ready-url", f"http://127.0.0.1:{port}/health",
            "--http-get", f"http://127.0.0.1:{port}/health",
            "--expect-status", "200",
            "--expect-contains", '"status": "ok"',
            "--expect-json", '{"service": "demo"}',
            "--no-receipt",
            "--json",
        )
        self.assertEqual(proc_http.returncode, 0, msg=proc_http.stdout + proc_http.stderr)
        self.assertTrue(json.loads(proc_http.stdout)["ok"])
        self.assertFalse(_pid_alive(json.loads(pid_file.read_text(encoding="utf-8"))["pid"]))

        # 4. Ad-hoc --start + --http-get WITHOUT explicit --ready-url auto-waits for port
        port2 = _pick_free_port()
        pid_file2 = self.root / "adhoc_auto_pid.json"
        proc_auto = self._run_verify(
            "--start", f"{sys.executable} -B demo_server.py {port2} adhoc_auto_pid.json",
            "--http-get", f"http://127.0.0.1:{port2}/health",
            "--expect-status", "200",
            "--no-receipt",
        )
        self.assertEqual(proc_auto.returncode, 0, msg=proc_auto.stdout + proc_auto.stderr)
        self.assertIn("Result: PASS", proc_auto.stdout)
        self.assertFalse(_pid_alive(json.loads(pid_file2.read_text(encoding="utf-8"))["pid"]))

    def test_file_artifact_checks_pass_and_fail_cases(self) -> None:
        (self.root / "empty.txt").write_text("", encoding="utf-8")
        recipe = {
            "checks": [
                {"id": "ok-file", "kind": "file", "path": "artifact.txt", "must_exist": True, "non_empty": True, "contains": ["build ok"]},
                {"id": "absent-ok", "kind": "file", "path": "does_not_exist.bin", "must_exist": False},
                {"id": "empty-fail", "kind": "file", "path": "empty.txt", "must_exist": True, "non_empty": True},
                {"id": "missing-fail", "kind": "file", "path": "missing.txt", "must_exist": True},
                {"id": "substr-fail", "kind": "file", "path": "artifact.txt", "contains": ["not-present"]},
            ]
        }
        report = verify.run_verification(recipe, repo_root=self.root, write_receipt=False)
        self.assertFalse(report["ok"])
        self.assertEqual(report["exit_code"], 1)
        by_id = {c["id"]: c for c in report["checks"]}
        self.assertTrue(by_id["ok-file"]["ok"])
        self.assertTrue(by_id["absent-ok"]["ok"])
        self.assertFalse(by_id["empty-fail"]["ok"])
        self.assertFalse(by_id["missing-fail"]["ok"])
        self.assertFalse(by_id["substr-fail"]["ok"])

    def test_receipt_invalidation_on_edit_commit_tamper_and_failed_run(self) -> None:
        # Missing receipt fails cleanly.
        chk_missing = self._run_verify("--check-receipt", "--json")
        self.assertEqual(chk_missing.returncode, 1)
        self.assertIn("not found", json.loads(chk_missing.stdout)["reason"])

        # Passing ad-hoc run creates valid receipt.
        proc = self._run_verify("--cmd", f"{sys.executable} -B app.py", "--expect-stdout", "app-v1")
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        receipt_file = self.root / ".anti-slop/last-verify.json"
        self.assertTrue(receipt_file.is_file())
        saved_receipt = receipt_file.read_text(encoding="utf-8")

        chk_fresh = self._run_verify("--check-receipt")
        self.assertEqual(chk_fresh.returncode, 0, msg=chk_fresh.stdout + chk_fresh.stderr)
        self.assertIn("VALID", chk_fresh.stdout)

        # 1. Modifying a tracked file invalidates --check-receipt!
        (self.root / "app.py").write_text("print('app-v2-unverified')\n", encoding="utf-8")
        chk_dirty = self._run_verify("--check-receipt", "--json")
        self.assertEqual(chk_dirty.returncode, 1)
        self.assertIn("working tree changed", json.loads(chk_dirty.stdout)["reason"])

        # Restore app.py -> valid again.
        (self.root / "app.py").write_text("print('app-v1')\n", encoding="utf-8")
        self.assertEqual(self._run_verify("--check-receipt").returncode, 0)

        # Adding/editing an untracked file also invalidates --check-receipt!
        untracked = self.root / "untracked_note.txt"
        untracked.write_text("v1\n", encoding="utf-8")
        self.assertEqual(self._run_verify("--check-receipt").returncode, 1)
        untracked.unlink()
        self.assertEqual(self._run_verify("--check-receipt").returncode, 0)

        # Custom --receipt path works cleanly for both write and --check-receipt.
        custom_rcpt = self.root / "custom/receipt.json"
        proc_custom = self._run_verify(
            "--cmd", f"{sys.executable} -B app.py",
            "--receipt", str(custom_rcpt),
            "--json",
        )
        self.assertEqual(proc_custom.returncode, 0, msg=proc_custom.stdout + proc_custom.stderr)
        self.assertTrue(custom_rcpt.is_file())
        self.assertEqual(self._run_verify("--check-receipt", "--receipt", str(custom_rcpt)).returncode, 0)
        custom_rcpt.unlink()
        custom_rcpt.parent.rmdir()
        self.assertEqual(self._run_verify("--check-receipt").returncode, 0)

        # 2. Tampering with last-verify.json fails integrity digest check!
        tampered = json.loads(saved_receipt)
        tampered["checks"][0]["observed"] = "forged output"
        receipt_file.write_text(json.dumps(tampered, indent=2), encoding="utf-8")
        chk_tamper = self._run_verify("--check-receipt", "--json")
        self.assertEqual(chk_tamper.returncode, 1)
        self.assertIn("integrity", json.loads(chk_tamper.stdout)["reason"])

        # Restore receipt, then advance git HEAD -> stale receipt!
        receipt_file.write_text(saved_receipt, encoding="utf-8")
        self.assertEqual(self._run_verify("--check-receipt").returncode, 0)
        (self.root / "extra.txt").write_text("new file\n", encoding="utf-8")
        subprocess.run(["git", "add", "extra.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "second commit"], cwd=self.root, check=True)
        chk_head = self._run_verify("--check-receipt", "--json")
        self.assertEqual(chk_head.returncode, 1)
        self.assertIn("git HEAD changed", json.loads(chk_head.stdout)["reason"])

        # 3. Failed check writes ok: false receipt and exits 1; --check-receipt rejects it!
        proc_fail = self._run_verify(
            "--cmd", f"{sys.executable} -B app.py",
            "--expect-stdout", "nonexistent-needle",
            "--json",
        )
        self.assertEqual(proc_fail.returncode, 1)
        self.assertFalse(json.loads(proc_fail.stdout)["ok"])
        receipt_after_fail = json.loads(receipt_file.read_text(encoding="utf-8"))
        self.assertFalse(receipt_after_fail["ok"])
        chk_failed_run = self._run_verify("--check-receipt", "--json")
        self.assertEqual(chk_failed_run.returncode, 1)
        self.assertIn("did not pass", json.loads(chk_failed_run.stdout)["reason"])

    def test_markdown_json_init_example_and_missing_recipe_exit_2(self) -> None:
        # --init-example prints valid JSON recipe.
        proc_init = self._run_verify("--init-example")
        self.assertEqual(proc_init.returncode, 0, msg=proc_init.stderr)
        parsed = json.loads(proc_init.stdout)
        verify.validate_recipe(parsed)

        # --markdown produces clean PR evidence table with zero em-dashes.
        proc_md = self._run_verify(
            "--cmd", f"{sys.executable} -B app.py",
            "--expect-stdout", "app-v1",
            "--file", "artifact.txt",
            "--markdown",
            "--no-receipt",
        )
        self.assertEqual(proc_md.returncode, 0, msg=proc_md.stdout + proc_md.stderr)
        self.assertIn("## Live Verification Evidence (Tier 1 E2E)", proc_md.stdout)
        self.assertIn("| Check | Kind | Result | Status | Elapsed | Observed Output |", proc_md.stdout)
        self.assertIn("| `cli-1` | `cli` | PASS |", proc_md.stdout)
        self.assertIn("| `file-1` | `file` | PASS |", proc_md.stdout)
        self.assertNotIn("\u2014", proc_md.stdout)

        # Missing default recipe exits 2 cleanly.
        proc_missing = self._run_verify()
        self.assertEqual(proc_missing.returncode, 2)
        self.assertIn("No verify recipe found", proc_missing.stderr)

        # Mixing --recipe and --cmd exits 2 cleanly.
        proc_mix = self._run_verify("--recipe", ".anti-slop/verify.json", "--cmd", "echo hi")
        self.assertEqual(proc_mix.returncode, 2)

    def test_http_mismatch_and_cli_timeout_failures(self) -> None:
        port = _pick_free_port()
        recipe = {
            "services": [
                {
                    "name": "demo",
                    "command": [sys.executable, "-B", "demo_server.py", str(port), "mismatch_pid.json"],
                    "ready_url": f"http://127.0.0.1:{port}/health",
                    "ready_timeout_s": 10,
                }
            ],
            "checks": [
                {
                    "id": "bad-json",
                    "kind": "http",
                    "url": f"http://127.0.0.1:{port}/health",
                    "expect_status": 200,
                    "expect_json": {"status": "wrong"},
                },
                {
                    "id": "bad-status",
                    "kind": "http",
                    "url": f"http://127.0.0.1:{port}/error",
                    "expect_status": 200,
                },
                {
                    "id": "slow-cli",
                    "kind": "cli",
                    "command": [sys.executable, "-c", "import time; time.sleep(30)"],
                    "timeout_s": 0.3,
                },
            ],
        }
        report = verify.run_verification(recipe, repo_root=self.root, write_receipt=False)
        self.assertFalse(report["ok"])
        self.assertEqual(report["exit_code"], 1)
        by_id = {c["id"]: c for c in report["checks"]}
        self.assertIn("expect_json mismatch", " ".join(by_id["bad-json"]["failures"]))
        self.assertIn("expected HTTP status 200, got 500", " ".join(by_id["bad-status"]["failures"]))
        self.assertIn("timed out", " ".join(by_id["slow-cli"]["failures"]))

        md = verify.format_report(report, markdown=True)
        self.assertIn("### Failures", md)
        self.assertIn("`bad-json`", md)
        self.assertFalse(_pid_alive(json.loads((self.root / "mismatch_pid.json").read_text(encoding="utf-8"))["pid"]))


if __name__ == "__main__":
    unittest.main()
