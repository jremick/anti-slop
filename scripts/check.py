#!/usr/bin/env python3
"""Run local/CI integrity checks without calling a model or a network service."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


KNOWN_COMPARISON_PAIRS: tuple[tuple[str, str], ...] = (
    ("baseline", "core-rules"),
    ("baseline", "core-rules-v0.1.0"),
    ("baseline", "core-rules-v0.2.0"),
    ("core-rules-v0.1.0", "core-rules-v0.2.0"),
    ("core-rules", "model-controls"),
    ("core-rules-v0.2.0", "model-controls"),
    ("baseline", "model-controls"),
    ("baseline", "gated-structural"),
    ("core-rules-v0.2.0", "gated-structural"),
    ("no-comments", "invariant-comments"),
    ("no-comments", "comment-traps"),
    ("invariant-comments", "comment-traps"),
)


def pilot_for_record(root: Path, record_path: Path) -> str:
    """Return the pilot manifest matching the case set recorded in a results JSONL."""
    case_keys: set[tuple[str, str]] = set()
    for line in record_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        cid, cver = record.get("case_id"), record.get("case_version")
        if isinstance(cid, str) and isinstance(cver, str):
            case_keys.add((cid, cver))
    for manifest in sorted((root / "benchmarks").glob("pilot*.json")):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        manifest_cases = {(c["case_id"], c["case_version"]) for c in data.get("cases", [])}
        if case_keys and case_keys <= manifest_cases:
            return str(manifest.relative_to(root))
    return "benchmarks/pilot.json"


def discover_summary_pairs(record_path: Path) -> list[tuple[str, str]]:
    """Return ordered (baseline, treatment) condition pairs present in measured records."""
    conditions: set[str] = set()
    for line in record_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("synthetic") is False and isinstance(record.get("condition"), str):
            conditions.add(record["condition"])
    if len(conditions) < 2:
        return []
    pairs = [pair for pair in KNOWN_COMPARISON_PAIRS if pair[0] in conditions and pair[1] in conditions]
    if pairs:
        return pairs
    ordered = sorted(conditions)
    if len(ordered) == 2:
        return [(ordered[0], ordered[1])]
    return []


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    results_dir = root / "results"
    record_paths = sorted(results_dir.rglob("*.jsonl")) if results_dir.is_dir() else []
    records = [str(path.relative_to(root)) for path in record_paths]
    commands = [
        [
            sys.executable, "-B", "scripts/benchmark.py",
            "--pilot", "benchmarks/pilot.json",
            "--run-record", "benchmarks/run-record.example.json",
            "validate",
            *records,
        ],
        [
            sys.executable, "-B", "scripts/benchmark.py",
            "--pilot", "benchmarks/pilot-v0.3.0.json",
            "validate",
        ],
        [
            sys.executable, "-B", "scripts/benchmark.py",
            "--pilot", "benchmarks/pilot-v0.4.0.json",
            "validate",
        ],
        [
            sys.executable, "-B", "scripts/benchmark.py",
            "--pilot", "benchmarks/pilot-v0.5.0.json",
            "validate",
        ],
        [
            sys.executable, "-B", "scripts/benchmark.py",
            "--pilot", "benchmarks/pilot-v0.6.0.json",
            "validate",
        ],
        [
            sys.executable, "-B", "scripts/benchmark.py",
            "--pilot", "benchmarks/pilot-evolution-v0.7.0.json",
            "validate",
        ],
        [
            sys.executable, "-B", "scripts/benchmark.py",
            "--pilot", "benchmarks/pilot-comments-v0.7.0.json",
            "validate",
        ],
        [
            sys.executable, "-B", "scripts/benchmark.py",
            "--pilot", "benchmarks/pilot-ts-evolution-v0.8.0.json",
            "validate",
        ],
        [
            sys.executable, "-B", "scripts/benchmark.py",
            "--pilot", "benchmarks/pilot-comments-v0.8.0.json",
            "validate",
        ],
        [
            sys.executable, "-B", "scripts/benchmark.py",
            "--pilot", "benchmarks/pilot-spec-fidelity-v0.9.0.json",
            "validate",
        ],
        [
            sys.executable, "-B", "scripts/benchmark.py",
            "--pilot", "benchmarks/pilot-spec-fidelity-greenfield-v0.9.0.json",
            "validate",
        ],
        [
            sys.executable, "-B", "benchmarks/graders/grade_cm1.py",
            "--check-ablation-fixtures",
        ],
        [
            sys.executable, "-B", "benchmarks/graders/grade_cm2.py",
            "--check-ablation-fixtures",
        ],
        [
            sys.executable, "-B", "-c",
            "import json; from gates.learn import validate_library_catalog; print(json.dumps(validate_library_catalog()))",
        ],
        [
            sys.executable, "-B", "-m", "unittest", "discover",
            "-s", "tests", "-p", "test_*.py", "-v",
        ],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=root, check=False)
        if result.returncode:
            return result.returncode
    for record_path in record_paths:
        rel = str(record_path.relative_to(root))
        pilot_rel = pilot_for_record(root, record_path)
        for baseline, treatment in discover_summary_pairs(record_path):
            result = subprocess.run(
                [
                    sys.executable, "-B", "scripts/benchmark.py",
                    "--pilot", pilot_rel,
                    "--baseline", baseline, "--treatment", treatment, "--json",
                    "summarize", rel,
                ],
                cwd=root,
                check=False,
            )
            if result.returncode:
                return result.returncode
    print("Repository checks passed. No model benchmark was executed by these checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
