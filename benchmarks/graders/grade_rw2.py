#!/usr/bin/env python3
"""Deterministic workspace grader for RW2 (pinned Python-Markdown real-work bugs).

Verifies Stage 1 (#1664 link brackets, #1726 footnotes, #1720 rule-of-3 emphasis linear-time
fixes + exact semantics) and Stage 2 (#1727 post-convert vs post-reset memory release contract)
against isolated candidate workspaces. Requires Python 3.11+ (upstream Python-Markdown 3.11).
"""

from __future__ import annotations

import argparse
from collections import Counter
import gc
from pathlib import Path
import re
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.graders import (  # noqa: E402
    build_report,
    emit_report,
    find_non_stdlib_imports,
    find_stub_or_placeholder_issues,
    load_candidate_package,
    make_check,
    parse_candidate_ast,
    sha256_file,
)

FIXTURE_REL = "benchmarks/sources/rw2_markdown"
READONLY_FILES = (
    "LICENSE.md",
    "UPSTREAM.json",
    "tests/test_smoke.py",
)


def _resolve_pkg_root(workspace_dir: Path) -> Path:
    nested = workspace_dir / FIXTURE_REL
    if nested.is_dir():
        return nested
    if (workspace_dir / "markdown").is_dir():
        return workspace_dir
    return nested


def _check_readonly_and_scope(workspace_dir: Path, pkg_root: Path) -> dict[str, Any]:
    ref_root = REPO_ROOT / FIXTURE_REL
    issues: list[str] = []

    for rel in READONLY_FILES:
        cand = pkg_root / rel
        ref = ref_root / rel
        if not cand.is_file():
            issues.append(f"frozen file missing: {rel}")
        elif sha256_file(cand) != sha256_file(ref):
            issues.append(f"frozen file modified: {rel}")

    ref_files = {
        str(p.relative_to(ref_root)).replace("\\", "/")
        for p in ref_root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    cand_files = {
        str(p.relative_to(pkg_root)).replace("\\", "/")
        for p in pkg_root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    extra_pkg = sorted(
        rel for rel in (cand_files - ref_files)
        if not re.fullmatch(r"tests/test_[A-Za-z0-9_]+\.py", rel)
    )
    if extra_pkg:
        issues.append(f"unexpected files created under rw2_markdown: {extra_pkg}")

    if workspace_dir.resolve() != pkg_root.resolve():
        stray: list[str] = []
        for p in sorted(workspace_dir.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts or p.suffix == ".pyc":
                continue
            rel = str(p.relative_to(workspace_dir)).replace("\\", "/")
            if rel == "AGENTS.md" or rel.startswith(FIXTURE_REL + "/"):
                continue
            stray.append(rel)
        if stray:
            issues.append(f"stray files left outside fixture tree: {stray}")

    for py_file in sorted((pkg_root / "markdown").rglob("*.py")):
        ref_py = ref_root / py_file.relative_to(pkg_root)
        if ref_py.is_file() and sha256_file(py_file) == sha256_file(ref_py):
            continue
        try:
            source, tree = parse_candidate_ast(py_file)
        except SyntaxError as exc:
            issues.append(f"syntax error in {py_file.name}: {exc}")
            continue
        bad_imports = find_non_stdlib_imports(tree, allowed_packages={"markdown"}, allow_relative=True)
        if bad_imports:
            issues.append(f"{py_file.name} imports non-stdlib modules: {bad_imports}")
        ref_counts: Counter[str] = Counter()
        if ref_py.is_file():
            ref_src, ref_tree = parse_candidate_ast(ref_py)
            ref_counts = Counter(re.sub(r" at line \d+$", "", s) for s in find_stub_or_placeholder_issues(ref_src, ref_tree))
        cand_counts = Counter(re.sub(r" at line \d+$", "", s) for s in find_stub_or_placeholder_issues(source, tree))
        new_stubs = sorted((cand_counts - ref_counts).elements())
        if new_stubs:
            issues.append(f"{py_file.name} introduced stub/placeholder: {new_stubs}")

    return make_check(
        "readonly_and_scope",
        not issues,
        "; ".join(issues) if issues else "frozen files unchanged, stdlib-only, zero new stubs or stray files",
    )


def grade(workspace_dir: Path, stage: int = 2) -> dict[str, Any]:
    pkg_root = _resolve_pkg_root(workspace_dir)
    if not (pkg_root / "markdown" / "__init__.py").is_file():
        return build_report("RW2", [make_check("load", False, f"markdown package not found under {workspace_dir}")])

    ro_check = _check_readonly_and_scope(workspace_dir, pkg_root)
    checks: list[dict[str, Any]] = []

    try:
        with load_candidate_package(pkg_root, "markdown") as markdown:
            from markdown.extensions.footnotes import FootnoteExtension
            from markdown.extensions.toc import TocExtension
            from markdown.treeprocessors import InlineProcessor

            # Check 1: #1664 link brackets + #1720 rule-of-3 emphasis (exact output + linear time)
            c1_issues: list[str] = []
            try:
                # Edge semantics for unclosed brackets
                out_nested = markdown.markdown("[[[Text](http://link.com) [more [text")
                exp_nested = '<p>[[<a href="http://link.com">Text</a> [more [text</p>'
                if out_nested != exp_nested:
                    c1_issues.append(f"unclosed nested brackets mismatch: got {out_nested!r}")

                # Image with unclosed brackets
                out_img = markdown.markdown("[[![alt](http://img.example/a.png) [tail")
                exp_img = '<p>[[<img alt="alt" src="http://img.example/a.png" /> [tail</p>'
                if out_img != exp_img:
                    c1_issues.append(f"unclosed image brackets mismatch: got {out_img!r}")

                # Linear-time check on 10,000 unclosed brackets (base takes >25s at N=10000, ~6.5s at N=5000)
                t0 = time.monotonic()
                out_big_links = markdown.markdown("[[" * 5000 + "[Text](http://link.com)")
                dt_links = time.monotonic() - t0
                exp_big_links = "<p>" + "[[" * 5000 + '<a href="http://link.com">Text</a></p>'
                if out_big_links != exp_big_links:
                    c1_issues.append("large unclosed brackets output mismatch")
                if dt_links > 1.5:
                    c1_issues.append(f"unclosed brackets still quadratic: {dt_links:.3f}s > 1.5s at N=5000")

                # Rule of 3 semantics + linear time at N=10000 (base takes ~2.0s; fixed <0.1s)
                out_r3_edge = markdown.markdown("***a**b*cd*e**f*g*h***")
                if out_r3_edge != "<p><em><strong>a</strong>b</em>cd<em>e**f</em>g<em>h</em>**</p>":
                    c1_issues.append(f"rule_of_3 edge mismatch: {out_r3_edge!r}")

                count = 10000
                t0 = time.monotonic()
                out_r3 = markdown.markdown("*a **b*a **b" * count)
                dt_r3 = time.monotonic() - t0
                exp_r3 = "<p>" + "<em>a **b</em>a **b" * count + "</p>"
                if out_r3 != exp_r3:
                    c1_issues.append("large rule_of_3 output mismatch")
                if dt_r3 > 0.8:
                    c1_issues.append(f"rule_of_3 delimiter scan still slow/quadratic: {dt_r3:.3f}s > 0.8s at N=10000")

                # Reused Markdown instance reset check on delimiters
                md_reuse = markdown.Markdown()
                a1 = md_reuse.convert("*a **b*a **b" * 50)
                md_reuse.reset()
                a2 = md_reuse.convert("*a **b*a **b" * 50)
                if a1 != a2:
                    c1_issues.append("reused Markdown instance produced differing emphasis after reset()")
            except Exception as exc:
                c1_issues.append(f"raised {type(exc).__name__}: {exc}")
            checks.append(make_check(
                "linear_time_links_and_emphasis",
                not c1_issues,
                "; ".join(c1_issues) if c1_issues else "link brackets and rule-of-3 emphasis verified linear-time and exact",
            ))

            # Check 2: #1726 duplicate footnote references (linear time + exact IDs + reset)
            c2_issues: list[str] = []
            try:
                n_fn = 3000
                ext = FootnoteExtension()
                md_fn = markdown.Markdown(extensions=[ext])
                t0 = time.monotonic()
                md_fn.convert("[^a]" * n_fn + "\n\n[^a]: A footnote.")
                dt_fn = time.monotonic() - t0
                expected_used = {"fnref:a"} | {f"fnref{i}:a" for i in range(2, n_fn + 1)}
                if ext.found_refs != {"fnref:a": n_fn}:
                    c2_issues.append(f"unexpected found_refs: {ext.found_refs!r}")
                if ext.used_refs != expected_used:
                    c2_issues.append("used_refs set mismatch for sequential footnote IDs")
                if dt_fn > 0.7:
                    c2_issues.append(f"duplicate footnotes still quadratic: {dt_fn:.3f}s > 0.7s at N={n_fn}")

                # Reset check across second document
                md_fn.reset()
                out2 = md_fn.convert("Ref[^a] and[^a].\n\n[^a]: Second doc.")
                if ext.found_refs != {"fnref:a": 2} or "fnref2:a" not in out2:
                    c2_issues.append("FootnoteExtension.reset() failed to clear duplicate tracking state")
            except Exception as exc:
                c2_issues.append(f"raised {type(exc).__name__}: {exc}")
            checks.append(make_check(
                "linear_time_footnotes",
                not c2_issues,
                "; ".join(c2_issues) if c2_issues else "duplicate footnote IDs verified linear-time, sequential, and reset-safe",
            ))

            # Check 3: Stage 2 (#1727 memory release contract)
            if stage >= 2:
                c3_issues: list[str] = []
                try:
                    md = markdown.Markdown(extensions=[TocExtension(), FootnoteExtension()])
                    doc = "# Title\n\nThis is a [link](https://example.com) with *emphasis*[^1].\n\n[^1]: Note.\n"
                    first = md.convert(doc)
                    inline = next(tp for tp in md.treeprocessors if isinstance(tp, InlineProcessor))

                    # Immediately after convert(): inline per-run caches MUST be cleared,
                    # while md.lines and md.parser.root MUST still be available until reset()!
                    if inline.parent_map != {}:
                        c3_issues.append(f"InlineProcessor.parent_map retained {len(inline.parent_map)} entries after convert()")
                    if inline.stashed_nodes != {}:
                        c3_issues.append(f"InlineProcessor.stashed_nodes retained {len(inline.stashed_nodes)} entries after convert()")
                    if not md.lines:
                        c3_issues.append("md.lines was cleared prematurely inside convert() instead of reset()")
                    if md.parser.root is None:
                        c3_issues.append("md.parser.root was cleared prematurely inside convert() instead of reset()")

                    # After reset(): md.lines and md.parser.root MUST be released and not retained by inline caches
                    sentinel_root = md.parser.root
                    md.reset()
                    if md.lines != []:
                        c3_issues.append(f"md.lines not empty after reset(): len={len(md.lines)}")
                    if md.parser.root is not None:
                        c3_issues.append("md.parser.root not None after reset()")
                    gc.collect()
                    # Only our local `sentinel_root` variable (plus temporary getrefcount/gc frame) should reference it;
                    # verify neither md nor any processor/inlinePattern retains sentinel_root.
                    retained_in = []
                    for owner_name, owner in [
                        ("md", md),
                        ("md.parser", md.parser),
                        ("InlineProcessor", inline),
                        *[(f"inlinePattern:{type(p).__name__}", p) for p in md.inlinePatterns],
                    ]:
                        owner_dict = getattr(owner, "__dict__", {})
                        if any(val is sentinel_root for val in owner_dict.values()):
                            retained_in.append(owner_name)
                    del sentinel_root
                    if retained_in:
                        c3_issues.append(f"old root Element still retained after reset() in {retained_in}")

                    # Second convert after reset must produce identical output and release cleanly again
                    second = md.convert(doc)
                    if second != first:
                        c3_issues.append("second convert() after reset() changed output")
                    if inline.parent_map != {} or inline.stashed_nodes != {}:
                        c3_issues.append("InlineProcessor caches not empty after second convert()")
                    md.reset()
                    if md.lines != [] or md.parser.root is not None:
                        c3_issues.append("second reset() failed to release md.lines / md.parser.root")
                except Exception as exc:
                    c3_issues.append(f"raised {type(exc).__name__}: {exc}")
                checks.append(make_check(
                    "document_memory_release",
                    not c3_issues,
                    "; ".join(c3_issues) if c3_issues else "InlineProcessor caches cleared post-convert; md.lines & md.parser.root preserved until reset()",
                ))
    except Exception as exc:
        checks.append(make_check("load", False, f"failed importing candidate markdown: {type(exc).__name__}: {exc}"))

    checks.append(ro_check)
    return build_report("RW2", checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--stage", type=int, choices=(1, 2), default=2)
    args = parser.parse_args(argv)
    return emit_report(grade(args.workspace, stage=args.stage))


if __name__ == "__main__":
    raise SystemExit(main())
