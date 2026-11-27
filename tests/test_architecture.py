"""Stdlib-only unit and integration tests for architectural slop detectors (gates/architecture.py).

Covers ARCH-CIRCULAR-IMPORT, ARCH-SINGLE-IMPL-WRAPPER, and ARCH-BOUNDARY-SCATTER
across Python and JS/TS bad cases, valid neighbouring exemptions, and CLI/API wiring
through gates/structural.py, gates/review.py, and gates/diff_check.py.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gates import architecture  # noqa: E402
from gates import diff_check  # noqa: E402
from gates import review  # noqa: E402
from gates import structural  # noqa: E402


def _codes(items) -> set[str]:
    return {item["code"] for item in items}


def _new_file_diff(rel_path: str, content: str) -> str:
    lines = content.splitlines()
    body = "".join(f"+{ln}\n" for ln in lines)
    return (
        f"diff --git a/{rel_path} b/{rel_path}\n"
        f"--- /dev/null\n"
        f"+++ b/{rel_path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}"
    )


class CircularImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_python_cycle_detection_and_symmetric_deduplication(self) -> None:
        pkg = self.root / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        a_src = "from . import b\n\ndef fa():\n    return b.fb()\n"
        b_src = "from pkg import a\n\ndef fb():\n    return a.fa()\n"
        (pkg / "a.py").write_text(a_src, encoding="utf-8")
        (pkg / "b.py").write_text(b_src, encoding="utf-8")

        # Both files in target_sources -> deduplicated to a single canonical cycle.
        hits = architecture.check_circular_imports(
            {"pkg/a.py": (a_src, {1}), "pkg/b.py": (b_src, {1})},
            repo_root=self.root,
        )
        self.assertEqual(len(hits), 1, msg=hits)
        self.assertEqual(hits[0]["code"], "ARCH-CIRCULAR-IMPORT")
        self.assertEqual(hits[0]["meta"]["chain"], "pkg/a.py -> pkg/b.py -> pkg/a.py")
        self.assertEqual(hits[0]["file"], "pkg/a.py")
        self.assertEqual(hits[0]["line"], 1)

        # 3-module cycle with src/ layout.
        src_pkg = self.root / "src" / "app"
        src_pkg.mkdir(parents=True)
        (src_pkg / "__init__.py").write_text("", encoding="utf-8")
        x_src = "import app.y\n"
        y_src = "from app.z import Z\n"
        z_src = "from .x import X\n"
        (src_pkg / "x.py").write_text(x_src, encoding="utf-8")
        (src_pkg / "y.py").write_text(y_src, encoding="utf-8")
        (src_pkg / "z.py").write_text(z_src, encoding="utf-8")
        hits3 = architecture.check_circular_imports(
            {"src/app/z.py": (z_src, {1})},
            repo_root=self.root,
        )
        self.assertEqual(len(hits3), 1, msg=hits3)
        self.assertEqual(
            hits3[0]["meta"]["chain"],
            "src/app/x.py -> src/app/y.py -> src/app/z.py -> src/app/x.py",
        )

    def test_python_exemptions_type_checking_tests_lazy_and_unrelated_diff(self) -> None:
        pkg = self.root / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from .a import A\nfrom .b import B\n", encoding="utf-8")
        a_src = (
            "from __future__ import annotations\n"
            "import typing\n"
            "from typing import TYPE_CHECKING\n"
            "from .b import B\n\n"
            "if TYPE_CHECKING:\n"
            "    from .c import C\n\n"
            "if typing.TYPE_CHECKING:\n"
            "    import pkg.d\n\n"
            "class A:\n"
            "    pass\n"
        )
        b_src = (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from .a import A\n\n"
            "class B:\n"
            "    def helper(self):\n"
            "        from .a import A\n"
            "        return A\n"
        )
        c_src = "from .a import A\nclass C:\n    pass\n"
        d_src = "from .a import A\nclass D:\n    pass\n"
        (pkg / "a.py").write_text(a_src, encoding="utf-8")
        (pkg / "b.py").write_text(b_src, encoding="utf-8")
        (pkg / "c.py").write_text(c_src, encoding="utf-8")
        (pkg / "d.py").write_text(d_src, encoding="utf-8")

        hits = architecture.check_circular_imports(
            {
                "pkg/a.py": (a_src, None),
                "pkg/b.py": (b_src, None),
                "pkg/c.py": (c_src, None),
                "pkg/d.py": (d_src, None),
            },
            repo_root=self.root,
        )
        self.assertEqual(hits, [], msg=hits)

        # Test files creating cycles are skipped.
        tests_dir = self.root / "tests"
        tests_dir.mkdir()
        t1 = "from tests import test_two\n"
        t2 = "from tests import test_one\n"
        (tests_dir / "test_one.py").write_text(t1, encoding="utf-8")
        (tests_dir / "test_two.py").write_text(t2, encoding="utf-8")
        self.assertEqual(
            architecture.check_circular_imports(
                {"tests/test_one.py": (t1, None), "tests/test_two.py": (t2, None)},
                repo_root=self.root,
            ),
            [],
        )

        # Pre-existing cycle is NOT blamed on an unrelated diff line edit.
        cyc_a = "from . import cyc_b\n\nVAL = 1\n"
        cyc_b = "from . import cyc_a\n\nVAL = 2\n"
        (pkg / "cyc_a.py").write_text(cyc_a, encoding="utf-8")
        (pkg / "cyc_b.py").write_text(cyc_b, encoding="utf-8")
        self.assertEqual(
            architecture.check_circular_imports({"pkg/cyc_a.py": (cyc_a, {3})}, repo_root=self.root),
            [],
        )
        # Touching line 1 (the cyclic import) IS flagged.
        self.assertEqual(
            len(architecture.check_circular_imports({"pkg/cyc_a.py": (cyc_a, {1})}, repo_root=self.root)),
            1,
        )

    def test_python_benchmarks_sources_skipped_for_normal_repo_scans(self) -> None:
        (self.root / "benchmarks/sources/case1").mkdir(parents=True)
        (self.root / "benchmarks/sources/case1/a.py").write_text("import b\n", encoding="utf-8")
        (self.root / "benchmarks/sources/case1/b.py").write_text("import a\n", encoding="utf-8")
        (self.root / "app").mkdir()
        (self.root / "app/main.py").write_text("X = 1\n", encoding="utf-8")

        # Scanning normal repo file ignores benchmarks/sources/.
        self.assertEqual(
            architecture.check_circular_imports({"app/main.py": ("X = 1\n", None)}, repo_root=self.root),
            [],
        )

        # Scanning inside an isolated benchmark workspace root (no benchmarks/sources/ prefix) detects it.
        iso_root = self.root / "benchmarks/sources/case1"
        iso_hits = architecture.check_circular_imports(
            {"a.py": ("import b\n", None)},
            repo_root=iso_root,
        )
        self.assertEqual(len(iso_hits), 1)
        self.assertEqual(iso_hits[0]["meta"]["chain"], "a.py -> b.py -> a.py")

    def test_js_ts_cycles_exact_lines_regex_and_type_only_exemptions(self) -> None:
        src = self.root / "src"
        src.mkdir()
        # 1. ESM .js -> .ts remapping + regex literal with `//` before import + exact line number.
        a_ts = (
            "const URL_RE = /https?:\\/\\//g\n"
            "import { helperB } from './b.js'\n"
            "export const runA = () => helperB(URL_RE)\n"
        )
        b_ts = (
            "import type { OnlyType } from './c'\n"
            "import { runA } from './a'\n"
            "export const helperB = (_r: RegExp) => runA()\n"
        )
        # Barrel export cycle: index.ts -> leaf.ts -> index.ts
        idx_ts = (
            "export type { LeafOpt } from './leaf'\n"
            "export { leafFn } from './leaf'\n"
        )
        leaf_ts = (
            "import { leafFn } from './'\n"
            "export type LeafOpt = { ok: boolean }\n"
            "export const leafFn = () => 1\n"
        )
        # Type-only imports and inline `import { type X }` must NOT create cycles.
        t1_ts = (
            "import type { T2 } from './t2'\n"
            "import { type HelperT2 } from './t2'\n"
            "export const v1 = 1\n"
        )
        t2_ts = (
            "import { v1 } from './t1'\n"
            "export type T2 = number\n"
            "export type HelperT2 = string\n"
            "export const v2 = v1 + 1\n"
        )
        # CommonJS require cycle.
        c1_js = "const c2 = require('./c2')\nmodule.exports = { c2 }\n"
        c2_js = "const c1 = require('./c1')\nmodule.exports = { c1 }\n"

        files = {
            "src/a.ts": a_ts,
            "src/b.ts": b_ts,
            "src/index.ts": idx_ts,
            "src/leaf.ts": leaf_ts,
            "src/t1.ts": t1_ts,
            "src/t2.ts": t2_ts,
            "src/c1.js": c1_js,
            "src/c2.js": c2_js,
        }
        for rel, content in files.items():
            (self.root / rel).write_text(content, encoding="utf-8")

        hits = architecture.check_circular_imports(
            {rel: (txt, None) for rel, txt in files.items()},
            repo_root=self.root,
        )
        chains = {h["meta"]["chain"]: (h["file"], h["line"]) for h in hits}
        self.assertEqual(
            set(chains.keys()),
            {
                "src/a.ts -> src/b.ts -> src/a.ts",
                "src/index.ts -> src/leaf.ts -> src/index.ts",
                "src/c1.js -> src/c2.js -> src/c1.js",
            },
            msg=hits,
        )
        # Exact 1-based line numbers (not off-by-one from preceding newline).
        self.assertEqual(chains["src/a.ts -> src/b.ts -> src/a.ts"], ("src/a.ts", 2))
        self.assertEqual(chains["src/index.ts -> src/leaf.ts -> src/index.ts"], ("src/index.ts", 2))


class SingleImplWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_python_single_impl_wrappers_and_exemptions(self) -> None:
        bad_py = (
            "from abc import ABC, abstractmethod\n"
            "from typing import Protocol\n\n"
            "class TaxStrategy(Protocol):\n"
            "    def compute(self, cents: int) -> int: ...\n\n"
            "class StandardTaxStrategy:\n"
            "    def compute(self, cents: int) -> int:\n"
            "        return (cents * 825 + 5000) // 10000\n\n"
            "class TaxStrategyFactory:\n"
            "    @staticmethod\n"
            "    def create() -> TaxStrategy:\n"
            "        return StandardTaxStrategy()\n\n"
            "class InvoiceStore(ABC):\n"
            "    @abstractmethod\n"
            "    def save(self, inv_id: str) -> None: ...\n\n"
            "class SqlInvoiceStore(InvoiceStore):\n"
            "    def save(self, inv_id: str) -> None:\n"
            "        print(inv_id)\n\n"
            "class PaymentWrapper:\n"
            "    def __init__(self, client):\n"
            "        self._client = client\n"
            "    def charge(self, amount):\n"
            "        return self._client.charge(amount)\n"
            "    def refund(self, tx_id):\n"
            "        return self._client.refund(tx_id)\n"
        )
        hits = architecture.check_single_impl_wrappers({"src/billing.py": (bad_py, None)})
        kinds = {(h["meta"]["kind"], h["meta"]["class"]) for h in hits}
        self.assertEqual(
            kinds,
            {
                ("python_protocol", "TaxStrategy"),
                ("python_factory", "TaxStrategyFactory"),
                ("python_abc", "InvoiceStore"),
                ("python_wrapper", "PaymentWrapper"),
            },
            msg=hits,
        )

        # Valid neighbouring cases: __all__ public interface, >=2 concrete impls, multi-impl factory,
        # nontrivial wrapper, dataclass/NamedTuple/TypedDict, TYPE_CHECKING/callable Protocol, test files.
        good_py = (
            "from abc import ABC, abstractmethod\n"
            "from dataclasses import dataclass\n"
            "from typing import NamedTuple, Protocol, TYPE_CHECKING, TypedDict\n\n"
            '__all__ = ["PublicPluginBase", "PublicServiceProtocol"]\n\n'
            "class PublicPluginBase(ABC):\n"
            "    @abstractmethod\n"
            "    def run(self) -> None: ...\n\n"
            "class PublicServiceProtocol(Protocol):\n"
            "    def handle(self, req: str) -> str: ...\n\n"
            "class RealStrategy(ABC):\n"
            "    @abstractmethod\n"
            "    def score(self, x: int) -> int: ...\n\n"
            "class FastStrategy(RealStrategy):\n"
            "    def score(self, x: int) -> int:\n"
            "        return x\n\n"
            "class SafeStrategy(RealStrategy):\n"
            "    def score(self, x: int) -> int:\n"
            "        return max(0, x)\n\n"
            "class StrategyFactory:\n"
            "    @staticmethod\n"
            "    def create(mode: str) -> RealStrategy:\n"
            "        if mode == 'fast':\n"
            "            return FastStrategy()\n"
            "        return SafeStrategy()\n\n"
            "class RetryingWrapper:\n"
            "    def __init__(self, client, retries: int = 3):\n"
            "        self._client = client\n"
            "        self._retries = retries\n"
            "    def send(self, payload):\n"
            "        for attempt in range(self._retries):\n"
            "            if attempt >= 0:\n"
            "                return self._client.send(payload)\n"
            "        raise RuntimeError('exhausted')\n\n"
            "@dataclass\n"
            "class OrderDTO:\n"
            "    order_id: str\n\n"
            "class Coord(NamedTuple):\n"
            "    x: int\n"
            "    y: int\n\n"
            "class PayloadDict(TypedDict):\n"
            "    amount: int\n\n"
            "class HandlerFn(Protocol):\n"
            "    def __call__(self, x: int) -> int: ...\n\n"
            "if TYPE_CHECKING:\n"
            "    class TypingOnlyProto(Protocol):\n"
            "        def parse(self, raw: str) -> dict: ...\n"
        )
        self.assertEqual(
            architecture.check_single_impl_wrappers({"src/good.py": (good_py, None)}),
            [],
        )
        # Test file containing speculative ABC is exempt.
        self.assertEqual(
            architecture.check_single_impl_wrappers({"tests/test_billing.py": (bad_py, None)}),
            [],
        )

    def test_js_ts_single_impl_wrappers_and_exemptions(self) -> None:
        bad_ts = (
            "export abstract class LedgerBase {\n"
            "  abstract record(amount: number): void;\n"
            "}\n"
            "export class MemoryLedger extends LedgerBase {\n"
            "  record(amount: number): void { console.log(amount); }\n"
            "}\n"
            "export interface PricingService {\n"
            "  calculate(subtotal: number): number;\n"
            "}\n"
            "export class PricingServiceImpl implements PricingService {\n"
            "  calculate(subtotal: number): number { return subtotal * 1.1; }\n"
            "}\n"
            "export class PricingFactory {\n"
            "  static create(): PricingService {\n"
            "    return new PricingServiceImpl();\n"
            "  }\n"
            "}\n"
            "export class ClientWrapper {\n"
            "  private inner: PricingService;\n"
            "  constructor(inner: PricingService) { this.inner = inner; }\n"
            "  calculate(subtotal: number): number {\n"
            "    return this.inner.calculate(subtotal);\n"
            "  }\n"
            "}\n"
        )
        hits = architecture.check_single_impl_wrappers({"src/pricing.ts": (bad_ts, None)})
        kinds = {h["meta"]["kind"] for h in hits}
        self.assertEqual(
            kinds,
            {"js_abstract_class", "js_interface_single_impl", "js_factory", "js_wrapper"},
            msg=hits,
        )

        # Valid neighbouring TS cases: plain data DTO interface, >=2 concrete impls/subclasses,
        # generic constraint `<E extends Base>` NOT miscounted as inheritance, pure-abstract types.ts stub.
        good_ts = (
            "export interface BookingDTO {\n"
            "  id: string;\n"
            "  nights: number;\n"
            "  guestName?: string;\n"
            "}\n"
            "export interface Router {\n"
            "  match(path: string): boolean;\n"
            "}\n"
            "export class TrieRouter implements Router {\n"
            "  match(path: string): boolean { return path.startsWith('/'); }\n"
            "}\n"
            "export class RegExpRouter implements Router {\n"
            "  match(path: string): boolean { return path.length > 0; }\n"
            "}\n"
            "export abstract class AdapterBase<E extends BookingDTO> {\n"
            "  abstract adapt(ev: E): string;\n"
            "}\n"
            "export class WebAdapter extends AdapterBase<BookingDTO> {\n"
            "  adapt(ev: BookingDTO): string { return ev.id; }\n"
            "}\n"
            "export class MobileAdapter extends AdapterBase<BookingDTO> {\n"
            "  adapt(ev: BookingDTO): string { return ev.id; }\n"
            "}\n"
            "export class RouterFactory {\n"
            "  static create(kind: string): Router {\n"
            "    if (kind === 'trie') { return new TrieRouter(); }\n"
            "    return new RegExpRouter();\n"
            "  }\n"
            "}\n"
        )
        types_ts = (
            "export abstract class FetchEventLike {\n"
            "  abstract readonly request: Request;\n"
            "  abstract respondWith(p: Promise<Response>): void;\n"
            "}\n"
        )
        self.assertEqual(
            architecture.check_single_impl_wrappers(
                {"src/router.ts": (good_ts, None), "src/types.ts": (types_ts, None)}
            ),
            [],
        )

        # Regression: `<T extends SoloBase>` must NOT exempt SoloBase as having >= 2 subclasses!
        generic_constraint_ts = (
            "export abstract class SoloBase {\n"
            "  abstract run(): void;\n"
            "}\n"
            "export class HelperA<T extends SoloBase> { item?: T; }\n"
            "export class HelperB<T extends SoloBase> { item?: T; }\n"
        )
        gen_hits = architecture.check_single_impl_wrappers({"src/solo.ts": (generic_constraint_ts, None)})
        self.assertEqual(len(gen_hits), 1, msg=gen_hits)
        self.assertEqual(gen_hits[0]["meta"]["class"], "SoloBase")


class BoundaryScatterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_python_env_scatter_and_exemptions(self) -> None:
        (self.root / "src").mkdir()
        (self.root / "src/a.py").write_text("import os\nDB = os.environ['DATABASE_URL']\n", encoding="utf-8")
        (self.root / "src/b.py").write_text("import os\nDB = os.environ.get('DATABASE_URL')\n", encoding="utf-8")
        c_src = "import os\nDB = os.getenv('DATABASE_URL')\n"
        (self.root / "src/c.py").write_text(c_src, encoding="utf-8")

        # Diff adding the 3rd production module triggers ARCH-BOUNDARY-SCATTER.
        hits = architecture.check_boundary_scatter({"src/c.py": (c_src, {2})}, repo_root=self.root)
        self.assertEqual(len(hits), 1, msg=hits)
        self.assertEqual(hits[0]["code"], "ARCH-BOUNDARY-SCATTER")
        self.assertEqual(hits[0]["file"], "src/c.py")
        self.assertEqual(hits[0]["line"], 2)
        self.assertEqual(hits[0]["meta"]["env_key"], "DATABASE_URL")
        self.assertEqual(hits[0]["meta"]["module_count"], 3)

        # Valid neighbouring cases:
        # 1. Centralized single config.py reading many env vars -> clean.
        cfg = (
            "import os\n"
            "DB = os.environ['DATABASE_URL']\n"
            "REDIS = os.getenv('REDIS_URL')\n"
            "API = os.environ.get('STRIPE_KEY')\n"
        )
        self.assertEqual(architecture.check_boundary_scatter({"src/config.py": (cfg, None)}), [])

        # 2. Universal runtime env vars scattered across 3 modules -> exempt.
        u_sources = {
            "src/u1.py": ("import os\nX = os.getenv('CI')\nY = os.getenv('PATH')\nZ = os.getenv('HOME')\n", None),
            "src/u2.py": ("import os\nX = os.environ.get('CI')\nY = os.environ.get('PATH')\nZ = os.environ.get('HOME')\n", None),
            "src/u3.py": ("import os\nX = os.environ['CI']\nY = os.environ['PATH']\nZ = os.environ['HOME']\n", None),
        }
        self.assertEqual(architecture.check_boundary_scatter(u_sources), [])

        # 3. Only 2 prod modules + 1 test module + 1 env write -> exempt (< 3 prod reads).
        two_plus_test = {
            "src/p1.py": ("import os\nV = os.getenv('TENANT_REGION')\n", None),
            "src/p2.py": ("import os\nV = os.getenv('TENANT_REGION')\n", None),
            "src/p3.py": ("import os\nos.environ['TENANT_REGION'] = 'us'\n", None),
            "tests/test_region.py": ("import os\nV = os.getenv('TENANT_REGION')\n", None),
        }
        self.assertEqual(architecture.check_boundary_scatter(two_plus_test), [])

    def test_js_ts_env_scatter_and_exemptions(self) -> None:
        bad_js = {
            "src/a.ts": ("export const url = process.env.BILLING_API_URL;\n", {1}),
            "src/b.ts": ("export const url = process.env['BILLING_API_URL'];\n", {1}),
            "src/c.ts": ('export const url = process.env["BILLING_API_URL"];\n', {1}),
        }
        hits = architecture.check_boundary_scatter(bad_js)
        self.assertEqual(len(hits), 1, msg=hits)
        self.assertEqual(hits[0]["code"], "ARCH-BOUNDARY-SCATTER")
        self.assertEqual(hits[0]["meta"]["env_key"], "BILLING_API_URL")

        # NODE_ENV / CI / DEBUG exempt, and comments/assignments ignored.
        good_js = {
            "src/a.ts": ("export const e = process.env.NODE_ENV;\nexport const c = process.env.CI;\n", None),
            "src/b.ts": ("export const e = process.env['NODE_ENV'];\nexport const c = process.env['CI'];\n", None),
            "src/c.ts": (
                "export const e = process.env.NODE_ENV;\n"
                "// process.env.STRIPE_SECRET\n"
                "process.env.STRIPE_SECRET = 'set';\n",
                None,
            ),
            "src/d.ts": ("export const s = process.env.STRIPE_SECRET;\n", None),
            "src/e.ts": ("export const s = process.env.STRIPE_SECRET;\n", None),
        }
        self.assertEqual(architecture.check_boundary_scatter(good_js), [])


class ArchitectureIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_review_and_diff_check_wiring_warning_and_strict_modes(self) -> None:
        (self.root / "pkg").mkdir()
        (self.root / "pkg/__init__.py").write_text("", encoding="utf-8")
        a_py = (
            "import os\n"
            "from pkg import b\n"
            "DB = os.getenv('APP_DB_DSN')\n"
            "def run_a():\n"
            "    return b.run_b(DB)\n"
        )
        b_py = (
            "import os\n"
            "from abc import ABC, abstractmethod\n"
            "from pkg import a\n"
            "DB = os.environ.get('APP_DB_DSN')\n"
            "class SoloRepo(ABC):\n"
            "    @abstractmethod\n"
            "    def get(self, k: str) -> str: ...\n"
            "class SqlSoloRepo(SoloRepo):\n"
            "    def get(self, k: str) -> str:\n"
            "        return k\n"
            "def run_b(val):\n"
            "    return val or a.DB\n"
        )
        c_py = "import os\nDB = os.environ['APP_DB_DSN']\n"

        (self.root / "pkg/a.py").write_text(a_py, encoding="utf-8")
        (self.root / "pkg/b.py").write_text(b_py, encoding="utf-8")
        (self.root / "pkg/c.py").write_text(c_py, encoding="utf-8")

        diff_txt = (
            _new_file_diff("pkg/a.py", a_py)
            + _new_file_diff("pkg/b.py", b_py)
            + _new_file_diff("pkg/c.py", c_py)
        )
        diff_file = self.root / "arch.diff"
        diff_file.write_text(diff_txt, encoding="utf-8")

        expected_arch = {
            "ARCH-CIRCULAR-IMPORT",
            "ARCH-SINGLE-IMPL-WRAPPER",
            "ARCH-BOUNDARY-SCATTER",
        }

        # 1. review.review_diff -> default warning severity with plain-English explanations & zero em-dashes.
        rep = review.review_diff(diff_txt, repo_root=self.root, strict_structural=False)
        self.assertTrue(rep["ok"], msg=rep)
        self.assertTrue(expected_arch.issubset(_codes(rep["warnings"])), msg=rep["warnings"])
        for item in rep["warnings"]:
            if item["code"] in expected_arch:
                exp = item["explanation"]
                self.assertIn("docs/evidence.md#ext-15", exp["evidence"])
                self.assertIn("docs/ai-era-rules.md", exp["evidence"])
                for val in exp.values():
                    self.assertNotIn("\u2014", val)

        # 2. review.review_files -> works identically in file-scan mode.
        rep_files = review.review_files(
            ["pkg/a.py", "pkg/b.py", "pkg/c.py"],
            repo_root=self.root,
            strict_structural=True,
        )
        self.assertFalse(rep_files["ok"])
        self.assertTrue(expected_arch.issubset(_codes(rep_files["errors"])), msg=rep_files["errors"])

        # 3. diff_check.py CLI --structural (warning, exit 0) vs --strict-structural (error, exit 1).
        proc_warn = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/diff_check.py"),
                "--diff", str(diff_file), "--repo-root", str(self.root),
                "--no-budget", "--structural", "--explain",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_warn.returncode, 0, msg=proc_warn.stderr)
        for code in expected_arch:
            self.assertIn(code, proc_warn.stderr)
        self.assertIn("docs/evidence.md#ext-15", proc_warn.stderr)

        proc_strict = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/diff_check.py"),
                "--diff", str(diff_file), "--repo-root", str(self.root),
                "--no-budget", "--strict-structural", "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_strict.returncode, 1)
        strict_data = json.loads(proc_strict.stdout)
        self.assertFalse(strict_data["ok"])
        self.assertTrue(expected_arch.issubset(_codes(strict_data["errors"])), msg=strict_data["errors"])


if __name__ == "__main__":
    unittest.main()
