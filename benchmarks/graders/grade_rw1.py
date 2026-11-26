#!/usr/bin/env python3
"""Deterministic workspace grader for RW1 (pinned python-poetry/tomlkit real-work bugs).

Verifies Stage 1 (#632/#717 out-of-order dotted-key super-table + #714/#716 deepcopy &
MAX_NESTING_DEPTH) and Stage 2 (#712 atomic non-table AoT rejection) against isolated
candidate workspaces without touching the repository fixtures.
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import re
import sys
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

FIXTURE_REL = "benchmarks/sources/rw1_tomlkit"
READONLY_FILES = (
    "LICENSE",
    "UPSTREAM.json",
    "pyproject.toml",
    "tests/test_smoke.py",
)


def _resolve_pkg_root(workspace_dir: Path) -> Path:
    nested = workspace_dir / FIXTURE_REL
    if nested.is_dir():
        return nested
    if (workspace_dir / "tomlkit").is_dir():
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
        issues.append(f"unexpected files created under rw1_tomlkit: {extra_pkg}")

    # Check workspace root for stray scratch files (ignoring AGENTS.md and fixture tree).
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

    for py_file in sorted((pkg_root / "tomlkit").rglob("*.py")):
        ref_py = ref_root / py_file.relative_to(pkg_root)
        if ref_py.is_file() and sha256_file(py_file) == sha256_file(ref_py):
            continue
        try:
            source, tree = parse_candidate_ast(py_file)
        except SyntaxError as exc:
            issues.append(f"syntax error in {py_file.name}: {exc}")
            continue
        bad_imports = find_non_stdlib_imports(
            tree, allowed_packages={"tomlkit", "typing_extensions"}, allow_relative=True
        )
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
    if not (pkg_root / "tomlkit" / "__init__.py").is_file():
        return build_report("RW1", [make_check("load", False, f"tomlkit package not found under {workspace_dir}")])

    ro_check = _check_readonly_and_scope(workspace_dir, pkg_root)
    checks: list[dict[str, Any]] = []

    try:
        with load_candidate_package(pkg_root, "tomlkit") as tomlkit:
            from tomlkit.exceptions import KeyAlreadyPresent, ParseError, TOMLKitError
            from tomlkit.parser import Parser

            # Check 1: #632/#717 out-of-order table header after multiple dotted keys
            c1_issues: list[str] = []
            try:
                content = (
                    "[a]\n"
                    "b.c = 1\n"
                    "b.d = 2\n\n"
                    "[x]\n"
                    "y = 1\n\n"
                    "[a.b.e]\n"
                    "f = 3\n"
                )
                doc = tomlkit.parse(content)
                expected = {
                    "a": {"b": {"c": 1, "d": 2, "e": {"f": 3}}},
                    "x": {"y": 1},
                }
                if doc.unwrap() != expected:
                    c1_issues.append(f"unexpected unwrap: {doc.unwrap()!r}")
                if doc.as_string() != content:
                    c1_issues.append("round-trip as_string() altered source layout")

                # Three dotted keys + out-of-order extension
                content2 = "[p]\nq.r = 1\nq.s = 2\nq.t = 3\n\n[other]\nk = true\n\n[p.q.u]\nv = 9\n"
                doc2 = tomlkit.parse(content2)
                if doc2.unwrap()["p"]["q"]["u"]["v"] != 9 or doc2.as_string() != content2:
                    c1_issues.append("three-dotted-key out-of-order round-trip failed")

                # Neighboring control: concrete table redefinition MUST stay rejected
                for bad in (
                    "[a.b]\nc = 1\n\n[a.b]\nd = 2\n",
                    "[a.b]\nc = 1\n\n[a]\nb.d = 2\n",
                    "[a]\nb.c = 1\nb.d = 2\n\n[x]\ny = 1\n\n[a.b.c]\nz = 3\n",
                ):
                    try:
                        tomlkit.parse(bad)
                        c1_issues.append(f"invalid redefinition was accepted: {bad!r}")
                    except (KeyAlreadyPresent, ParseError, TOMLKitError):
                        pass
            except Exception as exc:
                c1_issues.append(f"raised {type(exc).__name__}: {exc}")
            checks.append(make_check(
                "out_of_order_dotted_table",
                not c1_issues,
                "; ".join(c1_issues) if c1_issues else "out-of-order dotted-key super-table parses & round-trips; duplicates rejected",
            ))

            # Check 2: #714/#716 deepcopy & MAX_NESTING_DEPTH dotted key with sibling
            c2_issues: list[str] = []
            try:
                rec_limit_before = sys.getrecursionlimit()
                depth = Parser.MAX_NESTING_DEPTH
                if depth != 100:
                    c2_issues.append(f"Parser.MAX_NESTING_DEPTH was altered from 100 to {depth!r}")
                key = ".".join(["a"] * 100)
                doc_root = tomlkit.parse(f"{key} = 1\na.b = 2\n")
                if doc_root["a"]["b"] != 2:
                    c2_issues.append("root MAX_NESTING_DEPTH parse returned wrong value")
                doc_table = tomlkit.parse(f"[t]\n{key} = 1\na.b = 2\n")
                if doc_table["t"]["a"]["b"] != 2:
                    c2_issues.append("table MAX_NESTING_DEPTH parse returned wrong value")

                # Deepcopy at full 100-level nesting depth
                deep_clone = copy.deepcopy(doc_root)
                deep_clone["a"]["b"] = 999
                if doc_root["a"]["b"] != 2:
                    c2_issues.append("100-level deepcopy mutated original document")

                # Deepcopy isolation on Container, Table, and InlineTable
                orig = tomlkit.parse("[t]\nx = 1\nit = {k = 2}\n")
                cloned = copy.deepcopy(orig)
                cloned["t"]["x"] = 99
                cloned["t"]["it"]["k"] = 88
                if orig["t"]["x"] != 1 or orig["t"]["it"]["k"] != 2:
                    c2_issues.append("deepcopy mutated original Container/Table/InlineTable")
                tbl_clone = copy.deepcopy(orig["t"])
                tbl_clone["x"] = 77
                if orig["t"]["x"] != 1:
                    c2_issues.append("deepcopy on Table leaked mutation")
                it_clone = copy.deepcopy(orig["t"]["it"])
                it_clone["k"] = 66
                if orig["t"]["it"]["k"] != 2:
                    c2_issues.append("deepcopy on InlineTable leaked mutation")
                if sys.getrecursionlimit() != rec_limit_before:
                    c2_issues.append(
                        f"sys.setrecursionlimit() was mutated ({rec_limit_before} -> {sys.getrecursionlimit()})"
                    )
            except Exception as exc:
                c2_issues.append(f"raised {type(exc).__name__}: {exc}")
            checks.append(make_check(
                "deepcopy_and_nesting_limit",
                not c2_issues,
                "; ".join(c2_issues) if c2_issues else "MAX_NESTING_DEPTH root/table parse and Container/Table/InlineTable deepcopy verified",
            ))

            # Check 3: Stage 2 (#712 atomic non-table AoT assignment rejection)
            if stage >= 2:
                c3_issues: list[str] = []
                try:
                    source = "[[a]]\nx = 1\n[[a]]\nx = 2\n[[a]]\nx = 3\n"
                    indices: list[int | slice] = [0, -1, slice(None), slice(None, None, 2), slice(None, None, -2)]
                    invalids: list[Any] = [42, "text", [1, 2], tomlkit.inline_table()]
                    for idx in indices:
                        for inv in invalids:
                            doc = tomlkit.parse(source)
                            replacement = [{"x": 3}, inv] if isinstance(idx, slice) else inv
                            try:
                                doc["a"][idx] = replacement
                                c3_issues.append(f"accepted invalid AoT assignment idx={idx!r} inv={inv!r}")
                                break
                            except ValueError:
                                pass
                            except Exception as exc:
                                c3_issues.append(f"wrong exception {type(exc).__name__} for idx={idx!r} inv={inv!r}")
                                break
                            if (
                                doc.as_string() != source
                                or doc["a"] != [{"x": 1}, {"x": 2}, {"x": 3}]
                                or doc.unwrap() != {"a": [{"x": 1}, {"x": 2}, {"x": 3}]}
                                or json.loads(json.dumps(doc)) != doc.unwrap()
                            ):
                                c3_issues.append(f"document mutated on rejected AoT assignment idx={idx!r} inv={inv!r}")
                                break
                        if c3_issues:
                            break

                    # Valid neighboring AoT assignments must keep working
                    doc_ok = tomlkit.parse(source)
                    doc_ok["a"][0] = {"x": 10}
                    doc_ok["a"][1:3] = [{"x": 20}, {"x": 30}]
                    if doc_ok.unwrap() != {"a": [{"x": 10}, {"x": 20}, {"x": 30}]}:
                        c3_issues.append("valid AoT table/dict assignments broke")
                    if tomlkit.parse(doc_ok.as_string()).unwrap() != doc_ok.unwrap():
                        c3_issues.append("valid AoT assignment produced unparseable TOML")
                except Exception as exc:
                    c3_issues.append(f"raised {type(exc).__name__}: {exc}")
                checks.append(make_check(
                    "aot_atomic_validation",
                    not c3_issues,
                    "; ".join(c3_issues) if c3_issues else "all non-table AoT item/slice assignments raise ValueError before mutation",
                ))
    except Exception as exc:
        checks.append(make_check("load", False, f"failed importing candidate tomlkit: {type(exc).__name__}: {exc}"))

    checks.append(ro_check)
    return build_report("RW1", checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--stage", type=int, choices=(1, 2), default=2)
    args = parser.parse_args(argv)
    return emit_report(grade(args.workspace, stage=args.stage))


if __name__ == "__main__":
    raise SystemExit(main())
