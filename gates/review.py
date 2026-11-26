#!/usr/bin/env python3
"""Plain-English anti-slop code review workflow.

Combines surface-shortcut checks (gates/diff_check.py), structural compounding-
slop detectors (gates/structural.py), and approved learned rules (gates/learn.py),
then explains each finding in plain English:
  - what was found (file:line)
  - why experienced engineers flag it even when the app appears to run
  - how it compounds across future AI coding sessions
  - what to fix (or paste back to your AI coding assistant)

Zero third-party dependencies (Python 3.11+ stdlib only).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

_PKG_PARENT = str(Path(__file__).resolve().parents[1])
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from gates import diff_check as _dc  # noqa: E402
from gates import learn as _learn  # noqa: E402
from gates import structural as _struct  # noqa: E402


PLAIN_ENGLISH_CATALOG: Dict[str, Dict[str, str]] = {
    "DIFF-TEST-SKIP": {
        "title": "A test was skipped instead of fixing the bug",
        "why_veterans_flag_it": (
            "Adding a skip marker makes the test suite report green without verifying the broken behavior. "
            "Skipped tests almost never get re-enabled."
        ),
        "how_it_compounds": (
            "Future AI sessions see skipped tests as normal in this repo and keep skipping failing checks "
            "instead of fixing root causes."
        ),
        "fix_prompt": "Remove the test skip annotation, fix the underlying code defect, and re-run the test suite.",
    },
    "DIFF-UNAUTHORIZED-TEST-EDIT": {
        "title": "Existing tests were edited while changing production code",
        "why_veterans_flag_it": (
            "When tests change at the same time as a bug fix, it is easy for an AI to loosen assertions "
            "to match buggy output rather than fixing the code."
        ),
        "how_it_compounds": (
            "Weakened tests quietly erode your safety net so later AI edits can break core features undetected."
        ),
        "fix_prompt": "Restore the existing test file untouched and fix the production code to satisfy it (or explain why the test contract itself must change).",
    },
    "DIFF-SUPPRESSION": {
        "title": "A linter or type-checker warning was silenced without explanation",
        "why_veterans_flag_it": (
            "Blanket ignore comments hide real type mismatches and bugs instead of resolving them, "
            "leaving reviewers with no idea whether the bypass is safe."
        ),
        "how_it_compounds": (
            "Once blanket suppressions appear, future AI turns mimic them to silence new warnings rather than fixing interfaces."
        ),
        "fix_prompt": "Fix the underlying lint or type error. If an external library truly requires a suppression, scope it to one specific rule code with a short reason.",
    },
    "DIFF-SILENT-CATCH": {
        "title": "Errors are being caught and silently ignored",
        "why_veterans_flag_it": (
            "Catching every possible error and doing nothing hides crashes, broken permissions, and bad data "
            "until something fails mysteriously far downstream."
        ),
        "how_it_compounds": (
            "Future AI debugging turns cannot see the real error trace, so they add speculative workarounds on top of a hidden failure."
        ),
        "fix_prompt": "Catch only the specific expected exception type, or log and re-raise unexpected errors instead of swallowing them.",
    },
    "DIFF-DEBUG-LEFTOVER": {
        "title": "An interactive debugger statement was left in the code",
        "why_veterans_flag_it": (
            "Calls like breakpoint() or debugger; freeze execution in production or CI runs."
        ),
        "how_it_compounds": (
            "Leftover debugging artifacts stall automated test runners and waste later sessions diagnosing hangs."
        ),
        "fix_prompt": "Delete the leftover debugger statement and re-run tests.",
    },
    "DIFF-HOST-PATH": {
        "title": "A personal computer file path was hardcoded",
        "why_veterans_flag_it": (
            "Paths containing your local username fail on every other machine or CI runner and leak workstation details."
        ),
        "how_it_compounds": (
            "Later AI turns copy the hardcoded path into tests, scripts, or docs, spreading environment-specific breakage."
        ),
        "fix_prompt": "Replace the hardcoded machine path with a repo-relative path, Path.home(), or an environment variable.",
    },
    "DIFF-STUB-TODO": {
        "title": "Unfinished TODO/FIXME placeholder left in new code",
        "why_veterans_flag_it": (
            "AI assistants frequently finish the easy parts of a task and leave a TODO comment where the hard edge case belongs."
        ),
        "how_it_compounds": (
            "Later sessions build on top of half-finished functions assuming they work completely."
        ),
        "fix_prompt": "Implement the missing logic now instead of leaving a TODO stub, or explicitly report why it is blocked.",
    },
    "DIFF-STUB-NOT-IMPLEMENTED": {
        "title": "Function raises NotImplementedError instead of working",
        "why_veterans_flag_it": (
            "Shipping a concrete function that raises NotImplementedError leaves a runtime landmine whenever that branch is reached."
        ),
        "how_it_compounds": (
            "Future AI sessions treat the function signature as an existing working API and wire callers into a broken stub."
        ),
        "fix_prompt": "Implement the concrete behavior (or mark an intentional interface method with @abstractmethod).",
    },
    "DIFF-STUB-PASS": {
        "title": "Concrete function body is an empty 'pass' placeholder",
        "why_veterans_flag_it": (
            "An empty function silently returns None while looking implemented to callers."
        ),
        "how_it_compounds": (
            "Later turns call the no-op function assuming side effects or validation actually happened."
        ),
        "fix_prompt": "Implement the function body or remove the unused placeholder.",
    },
    "DIFF-CHATBOT-OPENER": {
        "title": "Conversational AI opener leaked into docs or PR description",
        "why_veterans_flag_it": (
            "Phrases like 'Sure!' or 'Here is...' signal unedited chatbot paste in permanent project documentation."
        ),
        "how_it_compounds": (
            "Bloat in docs reduces readability and teaches later sessions to treat project docs as chat transcripts."
        ),
        "fix_prompt": "Delete the conversational opener and start directly with the technical fact or decision.",
    },
    "DIFF-CHATBOT-CLOSER": {
        "title": "Conversational AI sign-off leaked into docs or PR description",
        "why_veterans_flag_it": (
            "Sign-offs like 'Hope this helps' or 'Let me know if you need anything' add zero engineering information."
        ),
        "how_it_compounds": (
            "Repeated filler degrades PR review signal so reviewers skim past real caveats."
        ),
        "fix_prompt": "Remove the sign-off filler and end with concrete status or verification commands.",
    },
    "DIFF-BROKEN-DOC-PATH": {
        "title": "Documentation references a file path that does not exist",
        "why_veterans_flag_it": (
            "Stale or invented file paths waste human onboarding time and point contributors at the wrong code."
        ),
        "how_it_compounds": (
            "Future AI agents read your docs first; broken paths send them hunting for nonexistent files or recreating files that already exist elsewhere."
        ),
        "fix_prompt": "Update the path to the real repository file or remove the stale reference.",
    },
    "DIFF-DECORATIVE-EMOJI": {
        "title": "Decorative AI emojis in technical headings or PR text",
        "why_veterans_flag_it": (
            "Decorative emojis clutter logs, grep searches, and changelogs without adding clarity."
        ),
        "how_it_compounds": (
            "Later AI turns mirror the style of existing docs and inject more decorative noise."
        ),
        "fix_prompt": "Remove decorative emojis from technical headings and prose.",
    },
    "DIFF-MAX-NET-LOC": {
        "title": "Change is larger than the reviewable line budget",
        "why_veterans_flag_it": (
            "Large diffs hide subtle bugs because neither humans nor reviewers can verify hundreds of changed lines carefully."
        ),
        "how_it_compounds": (
            "Oversized AI turns mix unrelated edits and make rollback or root-cause bisecting painful."
        ),
        "fix_prompt": "Split this change into smaller, independently tested steps.",
    },
    "DIFF-MAX-FILES": {
        "title": "Change touches more files than the reviewable budget",
        "why_veterans_flag_it": (
            "Editing many files at once increases blast radius and accidental regressions."
        ),
        "how_it_compounds": (
            "Wide edits blur module boundaries and encourage later AI turns to edit everywhere at once."
        ),
        "fix_prompt": "Narrow the diff to only the files required for this task.",
    },
    "STRUCT-TEST-THEATER": {
        "title": "Tests that look green without actually proving the code works",
        "why_veterans_flag_it": (
            "Tests with zero assertions, tautologies like 'assert True', or heavy mocking without checking real outputs "
            "stay green even when you introduce an obvious bug."
        ),
        "how_it_compounds": (
            "Future AI turns trust the green test run and ship regressions believing the suite checked behavior that was never tested."
        ),
        "fix_prompt": (
            "Rewrite this test to call the real code with concrete inputs and assert specific outputs, state changes, "
            "or error conditions — verify it fails if you break the logic."
        ),
    },
    "STRUCT-SILENT-FALLBACK": {
        "title": "Silent fallback default hiding a real error or missing secret",
        "why_veterans_flag_it": (
            "Returning a made-up default (like 0, '', or a hardcoded secret string) inside a broad catch keeps a demo "
            "from crashing while quietly producing corrupted data or insecure defaults."
        ),
        "how_it_compounds": (
            "Later AI sessions build features assuming the returned value is trustworthy, turning a simple config or parsing error "
            "into hard-to-trace silent data corruption."
        ),
        "fix_prompt": (
            "Fail closed with a clear error when required inputs/secrets are invalid, or catch only the exact expected exception "
            "and log the failure explicitly."
        ),
    },
    "STRUCT-DUPLICATE-BLOCK": {
        "title": "Copy-pasted logic block that will drift out of sync",
        "why_veterans_flag_it": (
            "When the same business logic lives in two places, fixing a bug or changing a rule in one place silently leaves "
            "the other copy broken."
        ),
        "how_it_compounds": (
            "AI assistants strongly mimic nearby code. Once a block is duplicated once, later sessions copy it a third time "
            "and fix bugs in only whichever file happened to be open."
        ),
        "fix_prompt": "Extract or reuse one shared canonical helper function for this logic and call it from both places.",
    },
    "STRUCT-DEAD-COMPAT": {
        "title": "Dead code, unreachable branch, or leftover legacy compatibility path",
        "why_veterans_flag_it": (
            "Unreachable branches, unused private helpers, and uncalled '*_legacy'/'*_compat' functions clutter the codebase "
            "and make it unclear which path is actually active."
        ),
        "how_it_compounds": (
            "Future AI sessions cannot easily tell dead paths from live ones — they frequently edit or copy the abandoned "
            "legacy helper instead of the real code path."
        ),
        "fix_prompt": "Delete the unreachable branch, unused helper, or obsolete legacy shim cleanly and re-run tests.",
    },
    "STRUCT-GOD-FUNCTION": {
        "title": "Function is growing too long or tangled to reason about safely",
        "why_veterans_flag_it": (
            "Functions with dozens of lines and deeply nested branches pack multiple responsibilities together, "
            "making edge cases easy to miss and hard to unit-test."
        ),
        "how_it_compounds": (
            "AI models degrade fastest when patching long, high-branch functions — each new turn bolts on another 'if' branch "
            "instead of clarifying the structure."
        ),
        "fix_prompt": "Split this function into smaller single-purpose helpers with clear names and focused tests.",
    },
    "STRUCT-GOD-FILE": {
        "title": "File is growing into a monolith mixing multiple responsibilities",
        "why_veterans_flag_it": (
            "Very large files create tight coupling and force every feature change to wade through hundreds of unrelated lines."
        ),
        "how_it_compounds": (
            "Large files burn context window tokens on every AI turn and increase the chance of unintended side edits."
        ),
        "fix_prompt": "Extract cohesive pieces into a dedicated module before adding more code to this file.",
    },
    "STRUCT-SCOPE-SPRAWL": {
        "title": "Single change is sprawling across too many unrelated areas",
        "why_veterans_flag_it": (
            "AI coding sessions often perform unrequested 'while I am here' edits across unrelated modules, "
            "introducing regressions far outside the feature you asked for."
        ),
        "how_it_compounds": (
            "Sprawling edits make reviews superficial and leave half-refactored conventions scattered across the repo."
        ),
        "fix_prompt": "Revert unrelated edits outside the target module and keep this change focused on one clear goal.",
    },
}


def explain_finding(finding: Dict[str, Any]) -> Dict[str, str]:
    """Return a plain-English explanation block for any DIFF-*, STRUCT-*, or LEARNED-* finding."""
    code = str(finding.get("code") or "")
    if code in PLAIN_ENGLISH_CATALOG:
        return dict(PLAIN_ENGLISH_CATALOG[code])
    if code.startswith("LEARNED-"):
        meta = finding.get("meta") or {}
        title = str(meta.get("title") or f"Project learned rule ({code})")
        why = str(meta.get("why_it_matters") or "This pattern previously slipped through and was approved as a project rule.")
        desired = str(meta.get("desired_outcome") or finding.get("remediation") or "Follow the approved project pattern.")
        return {
            "title": f"Learned rule: {title}",
            "why_veterans_flag_it": why,
            "how_it_compounds": (
                "You previously caught this pattern in this repository; letting it back in trains future AI sessions "
                "to repeat the same defect."
            ),
            "fix_prompt": f"{finding.get('remediation', desired)}",
        }
    return {
        "title": code or "Code quality finding",
        "why_veterans_flag_it": str(finding.get("message") or "This pattern violates an enabled quality check."),
        "how_it_compounds": "Unresolved shortcuts accumulate and get imitated by future AI coding turns.",
        "fix_prompt": str(finding.get("remediation") or "Resolve the flagged defect and re-run checks."),
    }


def _attach_explanations(findings: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for item in findings:
        copy_item = dict(item)
        copy_item["explanation"] = explain_finding(item)
        enriched.append(copy_item)
    return enriched


def _resolve_learned_store(
    repo_root: Optional[Path | str],
    learned_rules: Optional[Path | str],
) -> Tuple[Optional[Path], bool]:
    """Return (store_path, explicit). Explicit paths fail closed if missing; default path is optional."""
    if learned_rules is not None:
        return Path(learned_rules), True
    if repo_root is not None:
        default_p = _learn.default_store_path(repo_root)
        if default_p.is_file():
            return default_p, False
    return None, False


def review_diff(
    diff_text: str,
    *,
    repo_root: Optional[Path | str] = None,
    allow_test_edit: bool = True,
    allow_test_skip: bool = False,
    no_budget: bool = True,
    max_net_loc: int = _dc.DEFAULT_MAX_NET_LOC,
    max_files: int = _dc.DEFAULT_MAX_FILES,
    strict_prose: bool = False,
    strict_structural: bool = False,
    pr_body: Optional[str] = None,
    learned_rules: Optional[Path | str] = None,
    max_func_lines: int = _struct.DEFAULT_MAX_FUNC_LINES,
    max_func_branches: int = _struct.DEFAULT_MAX_FUNC_BRANCHES,
    max_file_lines: int = _struct.DEFAULT_MAX_FILE_LINES,
    max_module_spread: int = _struct.DEFAULT_MAX_MODULE_SPREAD,
) -> Dict[str, Any]:
    """Run surface + structural + approved learned checks on a unified diff with plain-English explanations."""
    base = _dc.check_diff(
        diff_text,
        repo_root=repo_root,
        allow_test_edit=allow_test_edit,
        allow_test_skip=allow_test_skip,
        no_budget=no_budget,
        max_net_loc=max_net_loc,
        max_files=max_files,
        pr_body=pr_body,
        strict_prose=strict_prose,
    )
    struct_res = _struct.check_structural_diff(
        diff_text,
        repo_root=repo_root,
        strict_structural=strict_structural,
        max_func_lines=max_func_lines,
        max_func_branches=max_func_branches,
        max_file_lines=max_file_lines,
        max_module_spread=max_module_spread,
    )

    errors = list(base["errors"]) + list(struct_res["errors"])
    warnings = list(base["warnings"]) + list(struct_res["warnings"])

    store, explicit_store = _resolve_learned_store(repo_root, learned_rules)
    if store is not None:
        l_res = _learn.check_learned_rules_in_diff(
            diff_text,
            store,
            repo_root=repo_root,
            require_exists=explicit_store,
        )
        errors.extend(l_res["errors"])
        warnings.extend(l_res["warnings"])

    enriched_errors = _attach_explanations(errors)
    enriched_warnings = _attach_explanations(warnings)
    return {
        "ok": len(enriched_errors) == 0,
        "summary": {
            "must_fix_count": len(enriched_errors),
            "compounding_risk_count": len(enriched_warnings),
            "stats": base["stats"],
        },
        "errors": enriched_errors,
        "warnings": enriched_warnings,
    }


def review_files(
    files: Sequence[str | Path],
    *,
    repo_root: Optional[Path | str] = None,
    allow_test_edit: bool = True,
    allow_test_skip: bool = False,
    no_budget: bool = True,
    strict_prose: bool = False,
    strict_structural: bool = False,
    pr_body: Optional[str] = None,
    learned_rules: Optional[Path | str] = None,
    max_func_lines: int = _struct.DEFAULT_MAX_FUNC_LINES,
    max_func_branches: int = _struct.DEFAULT_MAX_FUNC_BRANCHES,
    max_file_lines: int = _struct.DEFAULT_MAX_FILE_LINES,
) -> Dict[str, Any]:
    """Run surface + structural + approved learned checks on explicit files with plain-English explanations."""
    base = _dc.check_files(
        files,
        repo_root=repo_root,
        allow_test_edit=allow_test_edit,
        allow_test_skip=allow_test_skip,
        no_budget=no_budget,
        pr_body=pr_body,
        strict_prose=strict_prose,
    )
    struct_res = _struct.check_structural_files(
        files,
        repo_root=repo_root,
        strict_structural=strict_structural,
        max_func_lines=max_func_lines,
        max_func_branches=max_func_branches,
        max_file_lines=max_file_lines,
    )
    errors = list(base["errors"]) + list(struct_res["errors"])
    warnings = list(base["warnings"]) + list(struct_res["warnings"])

    store, explicit_store = _resolve_learned_store(repo_root, learned_rules)
    if store is not None:
        l_res = _learn.check_learned_rules_in_files(
            files,
            store,
            repo_root=repo_root,
            require_exists=explicit_store,
        )
        errors.extend(l_res["errors"])
        warnings.extend(l_res["warnings"])

    enriched_errors = _attach_explanations(errors)
    enriched_warnings = _attach_explanations(warnings)
    return {
        "ok": len(enriched_errors) == 0,
        "summary": {
            "must_fix_count": len(enriched_errors),
            "compounding_risk_count": len(enriched_warnings),
            "stats": base["stats"],
        },
        "errors": enriched_errors,
        "warnings": enriched_warnings,
    }


def format_plain_english(report: Dict[str, Any], *, markdown: bool = False) -> str:
    """Format a review report in clear, non-jargony English."""
    errors = report["errors"]
    warnings = report["warnings"]
    if not errors and not warnings:
        return "Anti-slop review: Clean. No shortcuts or compounding slop patterns found."

    lines: List[str] = []
    if markdown:
        lines.append("## Anti-Slop Plain-English Review")
        lines.append("")
        lines.append(
            f"- **Must-fix shortcuts:** {len(errors)}"
        )
        lines.append(
            f"- **Compounding slop risks:** {len(warnings)}"
        )
        lines.append("")
    else:
        lines.append("Anti-Slop Plain-English Review")
        lines.append("==============================")
        lines.append(
            f"Must-fix shortcuts: {len(errors)} | Compounding slop risks: {len(warnings)}"
        )
        lines.append("")

    def _emit_section(heading: str, items: Sequence[Dict[str, Any]]) -> None:
        if not items:
            return
        if markdown:
            lines.append(f"### {heading}")
            lines.append("")
        else:
            lines.append(heading)
            lines.append("-" * len(heading))
        for idx, item in enumerate(items, start=1):
            exp = item.get("explanation") or explain_finding(item)
            loc = ""
            if "file" in item:
                loc = f"{item['file']}:{item['line']}" if "line" in item else str(item["file"])
            loc_str = f" ({loc})" if loc else ""
            if markdown:
                lines.append(f"{idx}. **{exp['title']}** `{item['code']}`{loc_str}")
                lines.append(f"   - **What was found:** {item['message']}")
                lines.append(f"   - **Why experienced engineers flag this:** {exp['why_veterans_flag_it']}")
                lines.append(f"   - **How it compounds in future AI turns:** {exp['how_it_compounds']}")
                lines.append(f"   - **How to fix:** {exp['fix_prompt']}")
                lines.append("")
            else:
                lines.append(f"{idx}. {exp['title']} [{item['code']}]{loc_str}")
                lines.append(f"   What was found: {item['message']}")
                lines.append(f"   Why engineers flag this: {exp['why_veterans_flag_it']}")
                lines.append(f"   How it compounds across AI turns: {exp['how_it_compounds']}")
                lines.append(f"   Fix / prompt to give your AI: {exp['fix_prompt']}")
                lines.append("")

    _emit_section("Must-Fix Shortcuts (Blocking)", errors)
    _emit_section("Compounding Slop Risks (Review Before Merging)", warnings)
    return "\n".join(lines).rstrip()


def _synthesize_untracked_diffs(repo_root: Path) -> str:
    """Build unified new-file diff chunks for untracked non-ignored code and Markdown files."""
    proc = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        return ""
    chunks: List[str] = []
    for raw_rel in proc.stdout.decode("utf-8", errors="replace").split("\0"):
        rel = _dc._normalize_relpath(raw_rel)
        if not rel:
            continue
        if not (_dc._is_code_path(rel) or _dc._is_markdown_path(rel)):
            continue
        parts = Path(rel).parts
        if any(p in _struct.EXCLUDED_SCAN_DIRS for p in parts):
            continue
        disk_path = repo_root / rel
        if not disk_path.is_file():
            continue
        try:
            text = disk_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines()
        if not lines:
            continue
        body = "".join(f"+{ln}\n" for ln in lines)
        chunks.append(
            f"diff --git a/{rel} b/{rel}\n"
            f"--- /dev/null\n"
            f"+++ b/{rel}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n"
            f"{body}"
        )
    return "".join(chunks)


def _collect_git_diff(
    repo_root: Path,
    *,
    base_ref: Optional[str] = None,
    include_untracked: bool = True,
) -> Tuple[int, str, str]:
    if base_ref:
        proc = subprocess.run(
            ["git", "diff", "--unified=3", f"{base_ref}...HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr

    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if head.returncode == 0:
        proc = subprocess.run(
            ["git", "diff", "--unified=3", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--unified=3"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    if proc.returncode != 0:
        return proc.returncode, proc.stdout, proc.stderr

    diff_text = proc.stdout
    if include_untracked:
        untracked = _synthesize_untracked_diffs(repo_root)
        if untracked:
            if diff_text and not diff_text.endswith("\n"):
                diff_text += "\n"
            diff_text += untracked
    return 0, diff_text, proc.stderr


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a plain-English anti-slop review (shortcuts + structural compounding slop "
            "+ approved learned rules) on your current git diff, a diff file, or explicit files."
        )
    )
    parser.add_argument("--diff", default=None, help="Path to unified diff, or '-' for stdin.")
    parser.add_argument("--base", default=None, help="Git base ref to diff against (e.g., origin/main).")
    parser.add_argument("--no-untracked", action="store_true", help="Exclude untracked files when reviewing the git working tree.")
    parser.add_argument("--files", nargs="+", default=None, help="Explicit files to review.")
    parser.add_argument("--repo-root", default=".", help="Repository root (default: '.').")
    parser.add_argument("--lock-tests", action="store_true", help="Flag any edits under tests/.")
    parser.add_argument("--allow-test-skip", action="store_true", help="Allow test-skip annotations.")
    parser.add_argument("--strict-structural", action="store_true", help="Treat structural compounding slop as blocking errors.")
    parser.add_argument("--fail-on-warning", action="store_true", help="Exit 1 if any compounding slop risks are found.")
    parser.add_argument("--learned-rules", default=None, help="Path to learned rules JSON store.")
    parser.add_argument("--pr-body", default=None, help="Optional PR description text to review.")
    parser.add_argument("--pr-body-file", default=None, help="File containing PR description text.")
    parser.add_argument("--markdown", action="store_true", help="Format output as Markdown.")
    parser.add_argument("--json", action="store_true", dest="emit_json", help="Emit structured JSON.")
    parser.add_argument("paths", nargs="*", metavar="PATH", help="Optional positional file paths.")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    try:
        pr_body = args.pr_body
        if args.pr_body_file is not None:
            pr_body = Path(args.pr_body_file).read_text(encoding="utf-8")

        target_files = list(args.files or []) + list(args.paths or [])
        allow_test_edit = not args.lock_tests

        if target_files:
            report = review_files(
                target_files,
                repo_root=root,
                allow_test_edit=allow_test_edit,
                allow_test_skip=args.allow_test_skip,
                strict_structural=args.strict_structural,
                pr_body=pr_body,
                learned_rules=args.learned_rules,
            )
        else:
            if args.diff is not None:
                diff_text = sys.stdin.read() if args.diff == "-" else Path(args.diff).read_text(encoding="utf-8")
            elif args.base is not None:
                rc, diff_text, git_err = _collect_git_diff(root, base_ref=args.base)
                if rc != 0:
                    print(f"error: unable to read git diff in {root}: {git_err.strip()}", file=sys.stderr)
                    return 2
            else:
                piped = "" if sys.stdin.isatty() else sys.stdin.read()
                if piped.strip():
                    diff_text = piped
                else:
                    rc, diff_text, git_err = _collect_git_diff(
                        root, include_untracked=not args.no_untracked
                    )
                    if rc != 0:
                        print(f"error: unable to read git diff in {root}: {git_err.strip()}", file=sys.stderr)
                        return 2
            report = review_diff(
                diff_text,
                repo_root=root,
                allow_test_edit=allow_test_edit,
                allow_test_skip=args.allow_test_skip,
                strict_structural=args.strict_structural,
                pr_body=pr_body,
                learned_rules=args.learned_rules,
            )
    except (OSError, ValueError) as exc:
        if args.emit_json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.emit_json:
        print(json.dumps(report, indent=2))
    else:
        print(format_plain_english(report, markdown=args.markdown))

    if not report["ok"]:
        return 1
    if args.fail_on_warning and report["warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
