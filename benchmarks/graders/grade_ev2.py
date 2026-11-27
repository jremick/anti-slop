#!/usr/bin/env python3
"""Automated 4-turn TypeScript compounding quality & mutation grader for EV2 (ev2_ts_bookings).

Evaluates real compounding software quality across 4 sequential feature/refactor turns
with ZERO word-cap checks and ZERO third-party dependencies (Node native TS execution):
  1. `functional_all_turns`: hidden Node.js ES-module behavioral tests for Turn 1..stage.
  2. `mutation_test_strength`: diff/file JS/TS mutation testing via `gates/mutate.py`
     against the candidate's own test suite (`baseline.passed`, `kill_rate >= 0.65`,
     and 0 `STRUCT-TEST-THEATER`).
  3. `no_duplicate_code_growth`: 0 `STRUCT-DUPLICATE-BLOCK` findings across prod TS files.
  4. `no_dead_or_legacy_code`: 0 `STRUCT-DEAD-COMPAT` findings + clean Stage-4 removal of
     `legacyDepositMode`, `calculateLegacyDeposit`, `LEGACY_DEPOSIT_BPS`, and `depositCents`
     (plus zero unreachable `if (false)` branches or single-impl wrapper/factory shims).
  5. `no_sprawl_or_god_functions`: 0 `STRUCT-GOD-FUNCTION`, `STRUCT-GOD-FILE`, or
     `ARCH-CIRCULAR-IMPORT` findings, zero third-party npm imports, and <= 8 prod TS files.
  6. `no_silent_failures_or_shortcuts`: 0 `DIFF-*` findings, 0 `STRUCT-SILENT-FALLBACK`,
     and centralized `process.env` access (no `ARCH-BOUNDARY-SCATTER` outside `config.ts`).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.graders import build_report, emit_report, make_check  # noqa: E402
from gates import diff_check as _dc  # noqa: E402
from gates import mutate as _mutate  # noqa: E402
from gates import structural as _struct  # noqa: E402


CASE_ID = "EV2"
PACKAGE_NAME = "ev2_ts_bookings"
MIN_MUTATION_KILL_RATE = 0.65
MAX_PROD_FILES = 8
MAX_FUNC_LINES = 65
MAX_FUNC_BRANCHES = 14
MAX_FILE_LINES = 400

LEGACY_TOKENS: Tuple[str, ...] = (
    "legacyDepositMode",
    "calculateLegacyDeposit",
    "LEGACY_DEPOSIT_BPS",
    "depositCents",
)

TS_IMPORT_STMT_RE = re.compile(
    r"""(?:^|[;\n])\s*(?:import|export)\s+(?!type\b)(?:[^;\n'"]*?(?:\n[^;\n'"]*?)*?\bfrom\s+)?['"]([^'"]+)['"]"""
)
TS_DEAD_IF_RE = re.compile(r"\bif\s*\(\s*(?:false|0)\s*\)")
TS_PROCESS_ENV_RE = re.compile(r"\bprocess\.env\b")
TS_CANCEL_ENV_FALLBACK_RE = re.compile(
    r"""BOOKING_CANCEL_FEE_TIERS_JSON[^\n]*(?:\|\||\?\?)"""
)
TS_MULTILINE_CATCH_FALLBACK_RE = re.compile(
    r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*return\s+(?:null|undefined|false|true|-?\d+(?:\.\d+)?|''|\"\"|\[\]|\{\})\s*;?\s*\}",
    re.MULTILINE,
)
TS_WRAPPER_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?(?:abstract\s+class|class\s+[A-Za-z_$]\w*(?:Factory|Wrapper))\b"
)

HIDDEN_HARNESS_JS = r"""
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";

const [entryPath, stageRaw] = process.argv.slice(2);
const stage = Number(stageRaw);
const failures = [];

function check(label, fn) {
  try {
    fn();
  } catch (err) {
    failures.push(`${label}: ${err && err.message ? err.message : String(err)}`);
  }
}

try {
  const mod = await import(pathToFileURL(entryPath).href);
  const { BookingService, ValidationError, ConflictError, ConfigError } = mod;

  assert.equal(typeof BookingService, "function", "Missing BookingService export");
  assert.equal(typeof ValidationError, "function", "Missing ValidationError export");
  assert.equal(typeof ConflictError, "function", "Missing ConflictError export");
  assert.equal(typeof ConfigError, "function", "Missing ConfigError export");

  // Baseline whole-hour booking check.
  check("baseline", () => {
    const svc = new BookingService({ env: {} });
    svc.registerRoom({ roomId: "r_base", name: "Base", hourlyRateCents: 6000, taxBps: 1000 });
    const b = svc.createBooking({ roomId: "r_base", customerId: "c0", startMinute: 0, endMinute: 60 });
    assert.equal(b.subtotalCents, 6000);
    assert.equal(b.taxCents, 600);
    assert.equal(b.totalCents, 6600);
  });

  // Turn 1: half-up fractional-hour pricing, slot overlap, holds & expiration.
  if (stage >= 1) {
    check("turn1_pricing_half_up", () => {
      assert.equal(typeof mod.roundHalfUpDiv, "function", "Missing roundHalfUpDiv export");
      assert.equal(mod.roundHalfUpDiv(3, 2), 2);
      assert.equal(mod.roundHalfUpDiv(5, 2), 3);
      assert.equal(mod.roundHalfUpDiv(1005 * 1000, 10000), 101);
      assert.throws(() => mod.roundHalfUpDiv(-1, 2), ValidationError);
      assert.throws(() => mod.roundHalfUpDiv(1, 0), ValidationError);
      assert.throws(() => mod.roundHalfUpDiv(1.5, 2), ValidationError);

      const svc = new BookingService({ env: {} });
      svc.registerRoom({ roomId: "r1", name: "Room 1", hourlyRateCents: 1001, taxBps: 825 });
      // 90 min: 1001 * 90 / 60 = 1501.5 -> 1502; tax = 1502 * 825 / 10000 = 123.915 -> 124
      const b = svc.createBooking({ roomId: "r1", customerId: "c1", startMinute: 0, endMinute: 90, nowMinute: 0 });
      assert.equal(b.subtotalCents, 1502);
      assert.equal(b.taxCents, 124);
      assert.equal(b.totalCents, 1626);
    });

    check("turn1_overlap_and_holds", () => {
      assert.equal(typeof mod.slotsOverlap, "function", "Missing slotsOverlap export");
      assert.equal(typeof mod.isBookingActiveAt, "function", "Missing isBookingActiveAt export");
      assert.equal(mod.slotsOverlap(60, 120, 120, 180), false);
      assert.equal(mod.slotsOverlap(60, 120, 119, 180), true);
      assert.equal(mod.slotsOverlap(100, 150, 90, 101), true);

      const svc = new BookingService({ env: {} });
      svc.registerRoom({ roomId: "r1", name: "Room 1", hourlyRateCents: 4000, taxBps: 0 });
      const b1 = svc.createBooking({ roomId: "r1", customerId: "c1", startMinute: 60, endMinute: 120, nowMinute: 0 });
      assert.equal(b1.status, "confirmed");
      // Back-to-back allowed.
      const b2 = svc.createBooking({ roomId: "r1", customerId: "c2", startMinute: 120, endMinute: 180, nowMinute: 0 });
      assert.equal(b2.status, "confirmed");
      // Overlapping throws ConflictError.
      assert.throws(
        () => svc.createBooking({ roomId: "r1", customerId: "c3", startMinute: 110, endMinute: 130, nowMinute: 0 }),
        ConflictError,
      );

      // Hold expires at nowMinute >= expiresAt.
      const hold = svc.createBooking({
        roomId: "r1",
        customerId: "c_hold",
        startMinute: 300,
        endMinute: 360,
        nowMinute: 10,
        holdMinutes: 30,
      });
      assert.equal(hold.status, "held");
      assert.equal(hold.expiresAt, 40);
      assert.equal(mod.isBookingActiveAt(hold, 39), true);
      assert.equal(mod.isBookingActiveAt(hold, 40), false);
      assert.throws(
        () => svc.createBooking({ roomId: "r1", customerId: "c4", startMinute: 300, endMinute: 360, nowMinute: 39 }),
        ConflictError,
      );
      // Confirming expired hold fails.
      assert.throws(() => svc.confirmHold(hold.bookingId, 40), ValidationError);
      // Slot is free at nowMinute=40.
      const replaced = svc.createBooking({
        roomId: "r1",
        customerId: "c5",
        startMinute: 300,
        endMinute: 360,
        nowMinute: 40,
      });
      assert.equal(replaced.status, "confirmed");

      // Active hold confirmation locks slot permanently.
      const hold2 = svc.createBooking({
        roomId: "r1",
        customerId: "c_h2",
        startMinute: 500,
        endMinute: 560,
        nowMinute: 50,
        holdMinutes: 20,
      });
      const confirmed = svc.confirmHold(hold2.bookingId, 69);
      assert.equal(confirmed.status, "confirmed");
      assert.equal(confirmed.expiresAt, undefined);
      assert.throws(
        () => svc.createBooking({ roomId: "r1", customerId: "c6", startMinute: 500, endMinute: 560, nowMinute: 200 }),
        ConflictError,
      );
      // Invalid holdMinutes > maxHoldMinutes or <= 0 rejected.
      assert.throws(
        () => svc.createBooking({ roomId: "r1", customerId: "c7", startMinute: 700, endMinute: 760, nowMinute: 0, holdMinutes: 0 }),
        ValidationError,
      );
      assert.throws(
        () => svc.createBooking({ roomId: "r1", customerId: "c7", startMinute: 700, endMinute: 760, nowMinute: 0, holdMinutes: 61 }),
        ValidationError,
      );
    });
  }

  // Turn 2: Multi-room group/corporate bookings + shared applyDiscountAndTax.
  if (stage >= 2) {
    check("turn2_group_bookings_and_atomicity", () => {
      assert.equal(typeof mod.applyDiscountAndTax, "function", "Missing applyDiscountAndTax export");
      assert.equal(typeof mod.createGroupBooking, "function", "Missing createGroupBooking export");

      const d = mod.applyDiscountAndTax(1005, 1000, 825);
      // discount=101, subtotal=904, tax=roundHalfUpDiv(904*825, 10000)=75, total=979
      assert.deepEqual(d, { subtotalCents: 904, discountCents: 101, taxCents: 75, totalCents: 979 });

      const svc = new BookingService({ env: {} });
      svc.registerRoom({ roomId: "g1", name: "Hall 1", hourlyRateCents: 10000, taxBps: 1000 });
      svc.registerRoom({ roomId: "g2", name: "Hall 2", hourlyRateCents: 5000, taxBps: 1000 });
      svc.registerRoom({ roomId: "g3", name: "Hall 3", hourlyRateCents: 6000, taxBps: 825 });

      // 90 min: g1 gross=15000 (-1500=13500, tax=1350, tot=14850); g2 gross=7500 (-750=6750, tax=675, tot=7425)
      const grp = mod.createGroupBooking(svc, {
        customerId: "corp_acme",
        roomIds: ["g1", "g2"],
        startMinute: 100,
        endMinute: 190,
        discountBps: 1000,
        nowMinute: 0,
      });
      assert.ok(typeof grp.groupId === "string" && grp.groupId.length > 0);
      assert.equal(grp.bookings.length, 2);
      assert.equal(grp.bookings[0].groupId, grp.groupId);
      assert.equal(grp.bookings[1].groupId, grp.groupId);
      assert.equal(grp.discountCents, 2250);
      assert.equal(grp.subtotalCents, 20250);
      assert.equal(grp.taxCents, 2025);
      assert.equal(grp.totalCents, 22275);

      // Atomic rollback: g2 is busy at [300, 360), g3 is free. Group [g3, g2] must fail and leave g3 unbooked!
      svc.createBooking({ roomId: "g2", customerId: "blocker", startMinute: 300, endMinute: 360, nowMinute: 0 });
      const g3Before = svc.listRoomBookings("g3").length;
      assert.throws(
        () =>
          mod.createGroupBooking(svc, {
            customerId: "corp_fail",
            roomIds: ["g3", "g2"],
            startMinute: 300,
            endMinute: 360,
            discountBps: 500,
            nowMinute: 0,
          }),
        ConflictError,
      );
      assert.equal(svc.listRoomBookings("g3").length, g3Before, "Partial group booking leaked onto g3");

      // Reject < 2 rooms, duplicate rooms, invalid discount.
      assert.throws(
        () => mod.createGroupBooking(svc, { customerId: "c", roomIds: ["g3"], startMinute: 400, endMinute: 460, discountBps: 0 }),
        ValidationError,
      );
      assert.throws(
        () => mod.createGroupBooking(svc, { customerId: "c", roomIds: ["g3", "g3"], startMinute: 400, endMinute: 460, discountBps: 0 }),
        ValidationError,
      );
      assert.throws(
        () => mod.createGroupBooking(svc, { customerId: "c", roomIds: ["g1", "g3"], startMinute: 400, endMinute: 460, discountBps: 10001 }),
        ValidationError,
      );
    });
  }

  // Turn 3: Tiered cancellation refunds + centralized fail-closed config.
  if (stage >= 3) {
    check("turn3_cancellation_and_config_fail_closed", () => {
      assert.equal(typeof mod.loadCancellationFeeConfig, "function", "Missing loadCancellationFeeConfig export");
      assert.equal(typeof mod.selectCancellationFeeBps, "function", "Missing selectCancellationFeeBps export");
      assert.equal(typeof mod.computeCancellationRefund, "function", "Missing computeCancellationRefund export");

      const validJson = JSON.stringify({ cutoffMinutes: 1440, earlyFeeBps: 1000, lateFeeBps: 5000 });
      const cfg = mod.loadCancellationFeeConfig({ BOOKING_CANCEL_FEE_TIERS_JSON: validJson });
      assert.deepEqual(cfg, { cutoffMinutes: 1440, earlyFeeBps: 1000, lateFeeBps: 5000 });
      assert.equal(mod.selectCancellationFeeBps(1440, cfg), 1000);
      assert.equal(mod.selectCancellationFeeBps(1439, cfg), 5000);

      for (const badEnv of [
        {},
        { BOOKING_CANCEL_FEE_TIERS_JSON: "" },
        { BOOKING_CANCEL_FEE_TIERS_JSON: "{bad json" },
        { BOOKING_CANCEL_FEE_TIERS_JSON: JSON.stringify({ cutoffMinutes: -1, earlyFeeBps: 100, lateFeeBps: 200 }) },
        { BOOKING_CANCEL_FEE_TIERS_JSON: JSON.stringify({ cutoffMinutes: 60, earlyFeeBps: 10001, lateFeeBps: 200 }) },
      ]) {
        assert.throws(() => mod.loadCancellationFeeConfig(badEnv), ConfigError);
      }

      const svc = new BookingService({ env: { BOOKING_CANCEL_FEE_TIERS_JSON: validJson } });
      svc.registerRoom({ roomId: "c1", name: "Cancel Room", hourlyRateCents: 1005, taxBps: 0 });
      const bEarly = svc.createBooking({ roomId: "c1", customerId: "u1", startMinute: 2000, endMinute: 2060, nowMinute: 0 });
      const resEarly = svc.cancelBooking(bEarly.bookingId, 560); // 1440 min before start -> early 10% of 1005 = 101
      assert.equal(resEarly.feeBps, 1000);
      assert.equal(resEarly.feeCents, 101);
      assert.equal(resEarly.refundCents, 904);
      assert.equal(resEarly.booking.status, "cancelled");
      assert.equal(svc.getBooking(bEarly.bookingId).status, "cancelled");

      // Cancelled slot can be re-booked immediately.
      const bLate = svc.createBooking({ roomId: "c1", customerId: "u2", startMinute: 2000, endMinute: 2060, nowMinute: 600 });
      const resLate = svc.cancelBooking(bLate.bookingId, 1900); // 100 min < 1440 -> late 50% of 1005 = 503
      assert.equal(resLate.feeBps, 5000);
      assert.equal(resLate.feeCents, 503);
      assert.equal(resLate.refundCents, 502);
      // Double cancel rejected.
      assert.throws(() => svc.cancelBooking(bLate.bookingId, 1910), ValidationError);

      // Missing config fails closed WITHOUT cancelling booking!
      const svcBadCfg = new BookingService({ env: {} });
      svcBadCfg.registerRoom({ roomId: "c2", name: "NoCfg", hourlyRateCents: 2000, taxBps: 0 });
      const bStay = svcBadCfg.createBooking({ roomId: "c2", customerId: "u3", startMinute: 500, endMinute: 560, nowMinute: 0 });
      assert.throws(() => svcBadCfg.cancelBooking(bStay.bookingId, 100), ConfigError);
      assert.equal(svcBadCfg.getBooking(bStay.bookingId).status, "confirmed");
    });
  }

  // Turn 4: Complete removal of legacyDepositMode/calculateLegacyDeposit + fail-closed notifyHook.
  if (stage >= 4) {
    check("turn4_legacy_removed_and_notify_hook_atomic", () => {
      assert.equal(mod.calculateLegacyDeposit, undefined, "calculateLegacyDeposit must be removed");
      assert.equal(mod.LEGACY_DEPOSIT_BPS, undefined, "LEGACY_DEPOSIT_BPS must be removed");

      const validJson = JSON.stringify({ cutoffMinutes: 60, earlyFeeBps: 1000, lateFeeBps: 5000 });
      const events = [];
      const svc = new BookingService({
        env: { BOOKING_CANCEL_FEE_TIERS_JSON: validJson },
        notifyHook: (ev) => events.push(ev),
      });
      svc.registerRoom({ roomId: "n1", name: "Notify 1", hourlyRateCents: 1000, taxBps: 0 });
      svc.registerRoom({ roomId: "n2", name: "Notify 2", hourlyRateCents: 2000, taxBps: 0 });

      const b = svc.createBooking({ roomId: "n1", customerId: "cust_n", startMinute: 200, endMinute: 260, nowMinute: 0 });
      assert.equal("depositCents" in b, false, "depositCents must be removed from Booking");
      mod.createGroupBooking(svc, {
        customerId: "cust_g",
        roomIds: ["n1", "n2"],
        startMinute: 400,
        endMinute: 460,
        discountBps: 0,
        nowMinute: 0,
      });
      svc.cancelBooking(b.bookingId, 100);
      assert.equal(events.length, 4);
      assert.equal(events[0].event, "booking_created");
      assert.equal(events[0].bookingId, b.bookingId);
      assert.equal(events[0].amountCents, 1000);
      assert.equal(events[3].event, "booking_cancelled");
      assert.equal(events[3].bookingId, b.bookingId);
      assert.equal(events[3].amountCents, 900);

      // Fail-closed notifyHook: propagates AND rolls back create, group, and cancel!
      let failAfter = 999;
      let seen = 0;
      const svcFail = new BookingService({
        env: { BOOKING_CANCEL_FEE_TIERS_JSON: validJson },
        notifyHook: () => {
          seen += 1;
          if (seen > failAfter) {
            throw new Error("webhook offline");
          }
        },
      });
      svcFail.registerRoom({ roomId: "f1", name: "Fail 1", hourlyRateCents: 1000, taxBps: 0 });
      svcFail.registerRoom({ roomId: "f2", name: "Fail 2", hourlyRateCents: 1000, taxBps: 0 });
      const seed = svcFail.createBooking({ roomId: "f1", customerId: "seed", startMinute: 100, endMinute: 160, nowMinute: 0 });

      // Fail on createBooking.
      failAfter = seen;
      assert.throws(
        () => svcFail.createBooking({ roomId: "f1", customerId: "bad", startMinute: 200, endMinute: 260, nowMinute: 0 }),
        /webhook offline/,
      );
      assert.equal(svcFail.listRoomBookings("f1").length, 1);

      // Fail on 2nd room of createGroupBooking -> neither f1 nor f2 gets booked!
      failAfter = seen + 1;
      assert.throws(
        () =>
          mod.createGroupBooking(svcFail, {
            customerId: "bad_grp",
            roomIds: ["f1", "f2"],
            startMinute: 300,
            endMinute: 360,
            discountBps: 0,
            nowMinute: 0,
          }),
        /webhook offline/,
      );
      assert.equal(svcFail.listRoomBookings("f1").length, 1);
      assert.equal(svcFail.listRoomBookings("f2").length, 0);

      // Fail on cancelBooking -> seed booking remains confirmed!
      failAfter = seen;
      assert.throws(() => svcFail.cancelBooking(seed.bookingId, 10), /webhook offline/);
      assert.equal(svcFail.getBooking(seed.bookingId).status, "confirmed");
    });
  }
} catch (err) {
  failures.push(`harness error: ${err && err.message ? err.message : String(err)}`);
}

console.log(JSON.stringify({ ok: failures.length === 0, failures }));
process.exit(failures.length === 0 ? 0 : 1);
"""


def _resolve_package_dir(workspace: Path) -> Optional[Path]:
    candidates = [
        workspace / "benchmarks" / "sources" / PACKAGE_NAME,
        workspace / PACKAGE_NAME,
        workspace,
    ]
    for cand in candidates:
        if cand.is_dir() and (cand / "src" / "index.ts").is_file() and (cand / "run_checks.mjs").is_file():
            return cand
    return None


def _run_hidden_functional_tests(pkg_dir: Path, stage: int) -> Tuple[bool, str]:
    entry = pkg_dir / "src" / "index.ts"
    with tempfile.TemporaryDirectory(prefix="ev2_harness_") as tmp:
        harness_path = Path(tmp) / "harness.mjs"
        harness_path.write_text(HIDDEN_HARNESS_JS, encoding="utf-8")
        try:
            proc = subprocess.run(
                ["node", str(harness_path), str(entry), str(stage)],
                cwd=pkg_dir,
                capture_output=True,
                text=True,
                timeout=20.0,
                check=False,
            )
        except FileNotFoundError:
            return False, "node executable not found on PATH"
        except subprocess.TimeoutExpired:
            return False, "hidden EV2 Node test harness timed out"

    raw_out = (proc.stdout or "").strip()
    if raw_out:
        try:
            payload = json.loads(raw_out.splitlines()[-1])
            if payload.get("ok"):
                return True, f"All hidden TypeScript functional contracts passed through stage {stage}"
            failures = payload.get("failures") or []
            return False, "; ".join(str(x) for x in failures[:6])
        except ValueError:
            pass
    tail = ((proc.stderr or "") + "\n" + raw_out).strip()[-500:]
    return False, f"EV2 hidden harness failed (exit {proc.returncode}): {tail}"


def _collect_ts_files(pkg_dir: Path) -> Tuple[List[str], List[str], List[str]]:
    """Return (all_code_files, prod_ts_files, test_files) relative to pkg_dir."""
    all_code: List[str] = []
    prod_ts: List[str] = []
    test_files: List[str] = []
    for p in sorted(pkg_dir.rglob("*")):
        if not p.is_file():
            continue
        parts = p.relative_to(pkg_dir).parts
        if any(part in _struct.EXCLUDED_SCAN_DIRS for part in parts):
            continue
        rel = "/".join(parts)
        if not _dc._is_code_path(rel) and p.suffix.lower() not in _mutate.JS_TS_EXTENSIONS:
            continue
        all_code.append(rel)
        if _dc._is_test_file(rel):
            test_files.append(rel)
        elif rel != "run_checks.mjs" and p.suffix.lower() in _mutate.JS_TS_EXTENSIONS:
            prod_ts.append(rel)
    return all_code, prod_ts, test_files


def _strip_js_comments_keep_strings(source: str) -> str:
    """Remove // and /* */ comments while keeping string literal contents intact."""
    out: List[str] = []
    i = 0
    n = len(source)
    in_quote: Optional[str] = None
    in_block = False
    while i < n:
        ch = source[i]
        if in_block:
            if source[i : i + 2] == "*/":
                in_block = False
                out.append(" ")
                i += 2
            else:
                if ch == "\n":
                    out.append("\n")
                i += 1
            continue
        if in_quote is not None:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(source[i + 1])
                i += 2
                continue
            if ch == in_quote:
                in_quote = None
            i += 1
            continue
        if source[i : i + 2] == "//":
            while i < n and source[i] != "\n":
                i += 1
            continue
        if source[i : i + 2] == "/*":
            in_block = True
            i += 2
            continue
        if ch in ("'", '"', "`"):
            in_quote = ch
        out.append(ch)
        i += 1
    return "".join(out)


def _find_ts_import_cycles_and_third_party(
    pkg_dir: Path,
    prod_ts_files: Sequence[str],
) -> Tuple[List[str], List[str]]:
    """Detect static relative-import cycles (skipping `import type`) and non-builtin npm imports."""
    prod_set = set(prod_ts_files)
    graph: Dict[str, List[str]] = {rel: [] for rel in prod_ts_files}
    third_party: List[str] = []

    for rel in prod_ts_files:
        text = (pkg_dir / rel).read_text(encoding="utf-8")
        cleaned = _strip_js_comments_keep_strings(text)
        parent = (pkg_dir / rel).parent
        for m in TS_IMPORT_STMT_RE.finditer(cleaned):
            spec = m.group(1)
            if spec.startswith("node:"):
                continue
            if spec.startswith("."):
                resolved = (parent / spec).resolve()
                candidates = [resolved]
                if resolved.suffix == "":
                    candidates.extend([resolved.with_suffix(ext) for ext in (".ts", ".mts", ".js", ".mjs")])
                for cand in candidates:
                    if cand.is_file():
                        try:
                            target_rel = str(cand.relative_to(pkg_dir.resolve())).replace("\\", "/")
                        except ValueError:
                            continue
                        if target_rel in prod_set and target_rel not in graph[rel]:
                            graph[rel].append(target_rel)
                        break
            else:
                third_party.append(f"{rel}: third-party import '{spec}'")

    cycles: List[str] = []
    seen_canonical: Set[Tuple[str, ...]] = set()

    def _dfs(node: str, stack: List[str], on_stack: Set[str], visited: Set[str]) -> None:
        visited.add(node)
        stack.append(node)
        on_stack.add(node)
        for nxt in sorted(graph.get(node, ())):
            if nxt in on_stack:
                idx = stack.index(nxt)
                cyc = stack[idx:]
                min_pos = min(range(len(cyc)), key=lambda k: cyc[k])
                canon = tuple(cyc[min_pos:] + cyc[:min_pos])
                if canon not in seen_canonical:
                    seen_canonical.add(canon)
                    cycles.append(" -> ".join(list(canon) + [canon[0]]))
            elif nxt not in visited:
                _dfs(nxt, stack, on_stack, visited)
        stack.pop()
        on_stack.remove(node)

    visited: Set[str] = set()
    for node in sorted(graph):
        if node not in visited:
            _dfs(node, [], set(), visited)

    return cycles, third_party


def _check_ts_dead_legacy_and_env(
    pkg_dir: Path,
    prod_ts_files: Sequence[str],
    stage: int,
) -> Tuple[List[str], List[str]]:
    """Return (dead_legacy_issues, env_scatter_or_fallback_issues)."""
    dead_issues: List[str] = []
    env_issues: List[str] = []
    env_readers: List[str] = []

    for rel in prod_ts_files:
        text = (pkg_dir / rel).read_text(encoding="utf-8")
        code_lines, _ = _dc._scan_c_like_lines(text.splitlines())
        joined_code = "\n".join(code_lines)

        if stage >= 4:
            for tok in LEGACY_TOKENS:
                if re.search(rf"\b{re.escape(tok)}\b", joined_code):
                    dead_issues.append(f"{rel} still references removed legacy symbol '{tok}'")

        for idx, line in enumerate(code_lines, start=1):
            if TS_DEAD_IF_RE.search(line):
                dead_issues.append(f"{rel}:{idx} contains unreachable dead branch")
            if stage >= 4 and TS_WRAPPER_CLASS_RE.match(line):
                dead_issues.append(f"{rel}:{idx} defines speculative wrapper/factory abstraction")
            if TS_CANCEL_ENV_FALLBACK_RE.search(line):
                env_issues.append(f"{rel}:{idx} uses silent fallback on BOOKING_CANCEL_FEE_TIERS_JSON")

        if TS_MULTILINE_CATCH_FALLBACK_RE.search(joined_code):
            env_issues.append(f"{rel} contains silent catch returning a literal fallback")
        if TS_PROCESS_ENV_RE.search(joined_code):
            env_readers.append(rel)

    non_config_env = [r for r in env_readers if Path(r).name != "config.ts"]
    if len(non_config_env) >= 2:
        env_issues.append(
            f"process.env reads scattered outside src/config.ts across {len(non_config_env)} files: "
            + ", ".join(non_config_env)
        )
    return dead_issues, env_issues


def grade(
    workspace: Path | str,
    *,
    stage: int = 4,
    max_mutants: int = 20,
) -> Dict[str, Any]:
    """Mechanically grade an EV2 TypeScript 4-turn evolution workspace."""
    pkg_dir = _resolve_package_dir(Path(workspace).resolve())
    if pkg_dir is None:
        return build_report(
            CASE_ID,
            [make_check("functional_all_turns", False, f"Could not locate {PACKAGE_NAME}/ under {workspace}")],
        )

    all_code, prod_ts_files, _test_files = _collect_ts_files(pkg_dir)

    # 1. Hidden behavioral functional verification across turns 1..stage.
    func_ok, func_detail = _run_hidden_functional_tests(pkg_dir, stage)

    # 2. Surface diff_check + structural checks across workspace files.
    surface = _dc.check_files(
        all_code,
        repo_root=pkg_dir,
        allow_test_edit=True,
        allow_test_skip=False,
        no_budget=True,
    )
    structural = _struct.check_structural_files(
        all_code,
        repo_root=pkg_dir,
        strict_structural=False,
        max_func_lines=MAX_FUNC_LINES,
        max_func_branches=MAX_FUNC_BRANCHES,
        max_file_lines=MAX_FILE_LINES,
    )
    all_findings = (
        list(surface["errors"])
        + list(surface["warnings"])
        + list(structural["errors"])
        + list(structural["warnings"])
    )

    def _by_code(*codes: str) -> List[Dict[str, Any]]:
        cset = set(codes)
        return [f for f in all_findings if f["code"] in cset]

    # 3. JS/TS mutation testing via `gates/mutate.py` on all candidate prod TS modules.
    mut_report = _mutate.run_mutation_for_files(
        pkg_dir,
        prod_ts_files,
        test_cmd=["node", "run_checks.mjs"],
        max_mutants=max_mutants,
        min_kill_rate=MIN_MUTATION_KILL_RATE,
    )
    mut_summary = mut_report["summary"]
    mut_base_ok = bool(mut_report["baseline"]["passed"])
    mut_total = int(mut_summary["mutants_tested"])
    mut_killed = int(mut_summary["killed"])
    mut_kill_rate = float(mut_summary["kill_rate"] or 0.0)
    theater_findings = _by_code("STRUCT-TEST-THEATER")
    mut_ok = (
        mut_base_ok
        and mut_total >= 5
        and mut_kill_rate >= MIN_MUTATION_KILL_RATE
        and len(theater_findings) == 0
    )
    mut_detail = (
        f"baseline_tests_passed={mut_base_ok}, killed={mut_killed}/{mut_total} "
        f"({mut_kill_rate:.1%}, min {MIN_MUTATION_KILL_RATE:.0%}), test_theater={len(theater_findings)}"
    )
    if mut_report["survived_mutants"]:
        sample = [m["description"] for m in mut_report["survived_mutants"][:3]]
        mut_detail += f"; survived sample: {sample}"
    elif not mut_base_ok:
        mut_detail += f"; baseline_error={mut_report['baseline'].get('error')}"

    # 4. Duplicate code growth.
    dup_findings = _by_code("STRUCT-DUPLICATE-BLOCK")
    dup_ok = len(dup_findings) == 0
    dup_detail = (
        "0 duplicated logic blocks across production TS modules"
        if dup_ok
        else f"{len(dup_findings)} duplicate block(s): " + "; ".join(f["message"] for f in dup_findings[:3])
    )

    # 5. Dead / legacy code + Stage-4 removal.
    dead_struct = _by_code("STRUCT-DEAD-COMPAT", "ARCH-SINGLE-IMPL-WRAPPER")
    dead_ts_issues, env_issues = _check_ts_dead_legacy_and_env(pkg_dir, prod_ts_files, stage)
    dead_ok = len(dead_struct) == 0 and not dead_ts_issues
    dead_parts = [f["message"] for f in dead_struct[:3]] + dead_ts_issues[:4]
    dead_detail = (
        "0 dead/legacy paths" + (" and clean legacyDepositMode removal" if stage >= 4 else "")
        if dead_ok
        else "; ".join(dead_parts)
    )

    # 6. Sprawl, god functions/files, circular imports, zero npm deps.
    god_fns = _by_code("STRUCT-GOD-FUNCTION")
    god_files = _by_code("STRUCT-GOD-FILE")
    arch_cycles = _by_code("ARCH-CIRCULAR-IMPORT")
    static_cycles, third_party = _find_ts_import_cycles_and_third_party(pkg_dir, prod_ts_files)
    cycle_count = len(arch_cycles) + (0 if arch_cycles else len(static_cycles))
    sprawl_ok = (
        len(god_fns) == 0
        and len(god_files) == 0
        and cycle_count == 0
        and len(prod_ts_files) <= MAX_PROD_FILES
        and not third_party
    )
    sprawl_parts = [
        f"prod_ts_files={len(prod_ts_files)}/{MAX_PROD_FILES}",
        f"god_fns={len(god_fns)}",
        f"god_files={len(god_files)}",
        f"circular_imports={cycle_count}",
    ]
    if static_cycles:
        sprawl_parts.append("cycles=" + "; ".join(static_cycles[:2]))
    if third_party:
        sprawl_parts.append("; ".join(third_party[:2]))
    sprawl_detail = ", ".join(sprawl_parts)

    # 7. Silent failures, DIFF-* shortcuts, and boundary scatter.
    diff_and_silent = [
        f for f in all_findings
        if f["code"].startswith("DIFF-") or f["code"] in ("STRUCT-SILENT-FALLBACK", "ARCH-BOUNDARY-SCATTER")
    ]
    silent_ok = len(diff_and_silent) == 0 and not env_issues
    silent_parts = [f["message"] for f in diff_and_silent[:3]] + env_issues[:3]
    silent_detail = (
        "0 DIFF-* shortcuts, silent fallbacks, or scattered config reads"
        if silent_ok
        else "; ".join(silent_parts)
    )

    checks = [
        make_check("functional_all_turns", func_ok, func_detail),
        make_check("mutation_test_strength", mut_ok, mut_detail),
        make_check("no_duplicate_code_growth", dup_ok, dup_detail),
        make_check("no_dead_or_legacy_code", dead_ok, dead_detail),
        make_check("no_sprawl_or_god_functions", sprawl_ok, sprawl_detail),
        make_check("no_silent_failures_or_shortcuts", silent_ok, silent_detail),
    ]
    report = build_report(CASE_ID, checks)
    report["metrics"] = {
        "functional_passed": func_ok,
        "mutation_kill_rate": mut_kill_rate,
        "mutation_killed": mut_killed,
        "mutation_total": mut_total,
        "duplicate_blocks": len(dup_findings),
        "dead_compat": len(dead_struct) + len(dead_ts_issues),
        "god_functions": len(god_fns),
        "god_files": len(god_files),
        "circular_imports": cycle_count,
        "test_theater": len(theater_findings),
        "silent_failures_and_shortcuts": len(diff_and_silent) + len(env_issues),
        "prod_files_count": len(prod_ts_files),
    }
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Grade EV2 TypeScript 4-turn evolution workspace.")
    parser.add_argument("workspace", help="Path to candidate workspace containing ev2_ts_bookings/.")
    parser.add_argument("--stage", type=int, default=4, choices=(1, 2, 3, 4))
    parser.add_argument("--max-mutants", type=int, default=20)
    args = parser.parse_args(argv)
    report = grade(args.workspace, stage=args.stage, max_mutants=args.max_mutants)
    return emit_report(report)


if __name__ == "__main__":
    raise SystemExit(main())
