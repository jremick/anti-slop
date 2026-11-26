#!/usr/bin/env python3
"""Deterministic workspace grader for RW3 (pinned urllib3 streaming decoders + codec blocker gate).

Verifies:
- Hidden upstream regression tests for #5315 (multi-member gzip), #5316 (EOF flush + cache_content),
  and #5344 (atomic decode_content=False rejection preserving fp & buffer + read(0) == b'').
- Fail-closed optional brotli/zstd codec handling (not forged/mocked when third-party libs absent).
- Frozen read-only files unchanged (SHA-256) and stdlib-only hygiene.
- Stage 2 deterministic sign-off length (<= 75 lexical words) and zero-wrapper check when supplied.
"""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
from io import BytesIO
import itertools
from pathlib import Path
import re
import sys
import zlib
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.graders import (  # noqa: E402
    build_report,
    emit_report,
    find_non_stdlib_imports,
    find_stub_or_placeholder_issues,
    inspect_text_constraints,
    load_candidate_package,
    make_check,
    parse_candidate_ast,
    sha256_file,
)

FIXTURE_REL = "benchmarks/sources/rw3_urllib3"
READONLY_FILES = (
    "LICENSE.txt",
    "UPSTREAM.json",
    "run_checks.py",
    "tests/test_response_gates.py",
)
# Optional third-party imports already present upstream in urllib3 (guarded by try/except ImportError).
UPSTREAM_OPTIONAL_IMPORTS = {
    "urllib3",
    "backports",
    "brotli",
    "brotlicffi",
    "zstandard",
    "compression",
    "h2",
    "idna",
    "socks",
    "OpenSSL",
    "cryptography",
    "pyodide",
    "js",
    "typing_extensions",
}


def _resolve_pkg_root(workspace_dir: Path) -> Path:
    nested = workspace_dir / FIXTURE_REL
    if nested.is_dir():
        return nested
    if (workspace_dir / "src" / "urllib3").is_dir():
        return workspace_dir
    return nested


def _raw_deflate(payload: bytes) -> bytes:
    comp = zlib.compressobj(6, zlib.DEFLATED, -zlib.MAX_WBITS)
    return comp.compress(payload) + comp.flush()


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
    extra_pkg = sorted(cand_files - ref_files)
    if extra_pkg:
        issues.append(f"unexpected files created under rw3_urllib3: {extra_pkg}")

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

    for py_file in sorted((pkg_root / "src" / "urllib3").rglob("*.py")):
        ref_py = ref_root / py_file.relative_to(pkg_root)
        if ref_py.is_file() and sha256_file(py_file) == sha256_file(ref_py):
            continue
        try:
            source, tree = parse_candidate_ast(py_file)
        except SyntaxError as exc:
            issues.append(f"syntax error in {py_file.name}: {exc}")
            continue
        bad_imports = find_non_stdlib_imports(
            tree, allowed_packages=UPSTREAM_OPTIONAL_IMPORTS, allow_relative=True
        )
        if bad_imports:
            issues.append(f"{py_file.name} imports disallowed modules: {bad_imports}")
        ref_counts: Counter[str] = Counter()
        if ref_py.is_file():
            ref_src, ref_tree = parse_candidate_ast(ref_py)
            ref_counts = Counter(re.sub(r" at line \d+$", "", s) for s in find_stub_or_placeholder_issues(ref_src, ref_tree))
        cand_counts = Counter(re.sub(r" at line \d+$", "", s) for s in find_stub_or_placeholder_issues(source, tree))
        new_stubs = sorted((cand_counts - ref_counts).elements())
        if new_stubs:
            issues.append(f"{py_file.name} introduced stub/placeholder: {new_stubs}")

    return make_check(
        "readonly_and_no_test_tampering",
        not issues,
        "; ".join(issues) if issues else "frozen tests/runner/license unchanged, zero stray files or new stubs",
    )


def grade(
    workspace_dir: Path,
    stage: int = 2,
    response_file: Path | None = None,
) -> dict[str, Any]:
    pkg_root = _resolve_pkg_root(workspace_dir)
    src_dir = pkg_root / "src"
    if not (src_dir / "urllib3" / "response.py").is_file():
        return build_report("RW3", [make_check("load", False, f"urllib3 package not found under {workspace_dir}")])

    ro_check = _check_readonly_and_scope(workspace_dir, pkg_root)
    checks: list[dict[str, Any]] = []

    try:
        with load_candidate_package(src_dir, "urllib3"):
            import urllib3.response as resp_mod
            from urllib3.response import HTTPResponse

            # Check 1: #5315 + #5316 + #5344 hidden regression suite
            c1_issues: list[str] = []
            try:
                # #5315: multi-member gzip bounded read/read1 + bounded stream (guards infinite repeat bug)
                gz_two = gzip.compress(b"x" * 1024) + gzip.compress(b"y" * 1024)
                for method in ("read", "read1"):
                    r = HTTPResponse(BytesIO(gz_two), headers={"content-encoding": "gzip"}, preload_content=False)
                    fn = getattr(r, method)
                    if fn(1024) != b"x" * 1024 or fn(1024) != b"y" * 1024 or fn() != b"":
                        c1_issues.append(f"#5315 failed for {method}()")
                r_st = HTTPResponse(BytesIO(gz_two), headers={"content-encoding": "gzip"}, preload_content=False)
                st_chunks = list(itertools.islice(r_st.stream(1024), 5))
                if b"".join(st_chunks) != b"x" * 1024 + b"y" * 1024 or len(st_chunks) > 4:
                    c1_issues.append(f"#5315 failed for stream(1024): got {len(st_chunks)} chunks ({sum(len(c) for c in st_chunks)} bytes)")

                # #5316: raw deflate EOF flush across read, stream, read_then_read_all + chained deflate,gzip
                msg = b"abc" * 2000
                raw_def = _raw_deflate(msg)
                for mode in ("read", "stream", "read_then_read_all"):
                    r2 = HTTPResponse(BytesIO(raw_def), headers={"content-encoding": "deflate"}, preload_content=False)
                    if mode == "read":
                        got = b"".join(itertools.islice(iter(lambda: r2.read(64), b""), 256))
                    elif mode == "read_then_read_all":
                        got = r2.read(5952) + r2.read()
                    else:
                        got = b"".join(itertools.islice(r2.stream(64), 256))
                    if got != msg:
                        c1_issues.append(f"#5316 raw deflate truncated in mode={mode}: {len(got)}/{len(msg)}")

                gz_c = zlib.compressobj(6, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
                chained = gz_c.compress(_raw_deflate(b"abc" * 10)) + gz_c.flush()
                r2b = HTTPResponse(BytesIO(chained), headers={"content-encoding": "deflate, gzip"}, preload_content=False)
                if b"".join(itertools.islice(iter(lambda: r2b.read(1), b""), 128)) != b"abc" * 10:
                    c1_issues.append("#5316 chained deflate,gzip 1-byte reads failed")

                # #5316: cache_content=True second read must not clobber _body with b""
                for compress in (False, True):
                    fp_c = BytesIO(zlib.compress(b"foo") if compress else b"foo")
                    hdrs = {"content-encoding": "deflate"} if compress else None
                    rc = HTTPResponse(fp_c, headers=hdrs, preload_content=False)
                    if rc.read(cache_content=True) != b"foo" or rc.read(cache_content=True) != b"" or rc.data != b"foo":
                        c1_issues.append(f"#5316 cache_content clobbered _body (compress={compress})")

                # #5344: atomic decode_content=False rejection without consuming fp or buffered data
                for enc, comp_fn in (("gzip", gzip.compress), ("deflate", zlib.compress)):
                    for amt in (None, 1, -1):
                        fp3 = BytesIO(comp_fn(b"foo"))
                        r3 = HTTPResponse(fp3, headers={"content-encoding": enc}, preload_content=False)
                        if r3.read(1) != b"f":
                            c1_issues.append(f"#5344 setup read failed for {enc}")
                            continue
                        pos = fp3.tell()
                        try:
                            r3.read(amt, decode_content=False)
                            c1_issues.append(f"#5344 did not raise RuntimeError for enc={enc} amt={amt!r}")
                        except RuntimeError:
                            pass
                        if fp3.tell() != pos:
                            c1_issues.append(f"#5344 consumed fp before raising (enc={enc} amt={amt!r})")
                        if r3.read() != b"oo":
                            c1_issues.append(f"#5344 corrupted subsequent read() (enc={enc} amt={amt!r})")

                    # read(0, decode_content=False) must still return b"" without raising
                    fp0 = BytesIO(comp_fn(b"foo"))
                    r0 = HTTPResponse(fp0, headers={"content-encoding": enc}, preload_content=False)
                    if r0.read(1) != b"f":
                        c1_issues.append(f"#5344 read(0) setup failed for {enc}")
                    pos0 = fp0.tell()
                    if r0.read(0, decode_content=False) != b"" or fp0.tell() != pos0 or r0.read() != b"oo":
                        c1_issues.append(f"#5344 read(0, decode_content=False) failed for {enc}")

                # #5344 buffered-data case
                fp_buf = BytesIO(zlib.compress(b"foobarbaz"))
                r_buf = HTTPResponse(fp_buf, headers={"content-encoding": "deflate"}, preload_content=False)
                if r_buf.read(3) != b"foo":
                    c1_issues.append("#5344 buffered setup failed")
                dec = r_buf._decode(r_buf._raw_read(), decode_content=True, flush_decoder=False, max_length=3)
                r_buf._decoded_buffer.put(dec)
                try:
                    r_buf.read(1, decode_content=False)
                    c1_issues.append("#5344 buffered read(1, decode_content=False) did not raise RuntimeError")
                except RuntimeError:
                    pass
                if r_buf.read() != b"barbaz":
                    c1_issues.append("#5344 buffered data was lost on rejected toggle")
            except Exception as exc:
                c1_issues.append(f"raised {type(exc).__name__}: {exc}")
            checks.append(make_check(
                "streaming_decoder_fixes",
                not c1_issues,
                "; ".join(c1_issues) if c1_issues else "#5315, #5316, and #5344 streaming decoder regressions all pass",
            ))

            # Check 2: Fail-closed optional brotli/zstd codecs (must NOT forge availability or passthrough)
            c2_issues: list[str] = []
            try:
                # In a stdlib-only environment without brotli/brotlicffi installed, resp_mod.brotli must stay None
                real_brotli = False
                for mod_name in ("brotli", "brotlicffi"):
                    try:
                        __import__(mod_name)
                        real_brotli = True
                    except ImportError:
                        pass
                if not real_brotli:
                    if resp_mod.brotli is not None:
                        c2_issues.append(f"forged urllib3.response.brotli={resp_mod.brotli!r} when brotli is not installed")
                    # Ensure _get_decoder('br') does not fabricate a passthrough decoder
                    dec_br = resp_mod._get_decoder("br")
                    if dec_br is not None:
                        try:
                            out = dec_br.decompress(b"not-valid-brotli")
                            if out == b"not-valid-brotli":
                                c2_issues.append("fabricated passthrough BrotliDecoder fallback")
                        except Exception:
                            pass
                real_zstd = False
                for mod_name in ("compression.zstd", "zstandard"):
                    try:
                        __import__(mod_name)
                        real_zstd = True
                    except ImportError:
                        pass
                if not real_zstd and bool(getattr(resp_mod, "HAS_ZSTD", False)):
                    c2_issues.append("forged urllib3.response.HAS_ZSTD=True when zstandard is not installed")
            except Exception as exc:
                c2_issues.append(f"raised {type(exc).__name__}: {exc}")
            checks.append(make_check(
                "fail_closed_optional_codecs",
                not c2_issues,
                "; ".join(c2_issues) if c2_issues else "optional brotli/zstd codec gating remains fail-closed without stubs",
            ))
    except Exception as exc:
        checks.append(make_check("load", False, f"failed importing candidate urllib3: {type(exc).__name__}: {exc}"))

    checks.append(ro_check)

    if stage == 2 and response_file is not None and response_file.is_file():
        tc = inspect_text_constraints(response_file.read_text(encoding="utf-8"), max_words=75)
        checks.append(make_check(
            "brevity_and_zero_wrapper",
            tc["passed"],
            "; ".join(tc["issues"]) if tc["issues"] else f"Stage 2 sign-off {tc['lexical_words']}/75 lexical words (raw={tc['raw_words']}), zero wrapper/footer",
        ))

    return build_report("RW3", checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--stage", type=int, choices=(1, 2), default=2)
    parser.add_argument("--response-file", type=Path, default=None)
    args = parser.parse_args(argv)
    return emit_report(grade(args.workspace, stage=args.stage, response_file=args.response_file))


if __name__ == "__main__":
    raise SystemExit(main())
