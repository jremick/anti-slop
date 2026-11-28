# Automated Coding Graders

Seventeen zero-dependency, stdlib-only Python graders for single-file (`C1`, `C2`, `T1`, `P1`) and multi-file workspace (`M1`, `M2`, `B2`, `RW1`, `RW2`, `RW3`, `SE1`, `SE3`, `SE4`, `EV1`, `EV2`, `CM1`, `CM2`) coding benchmark cases. Each grader runs isolated static (AST/hygiene) and dynamic (contract/hidden-suite or Python & JS/TS mutation) checks and emits deterministic JSON evidence.

## Output contract

Every grader prints JSON to stdout:

```json
{
  "case_id": "C1",
  "passed": true,
  "checks": [
    {
      "id": "scope",
      "passed": true,
      "detail": "stdlib-only, no stubs, public API limited to total_by_category"
    }
  ]
}
```

- **Exit code `0`:** every check passed (`passed: true`).
- **Exit code `1`:** one or more checks failed (`passed: false`).
- **Non-compensatory:** a single failing check forces overall `passed: false`, matching `scripts/benchmark.py`.

## CLI usage

Run each grader from the repository root against a candidate artifact file (saving stdout as a project-relative check evidence file for `scripts/benchmark.py`):

```bash
python3 -B benchmarks/graders/grade_c1.py path/to/candidate_c1.py
python3 -B benchmarks/graders/grade_c2.py path/to/candidate_c2.py [--stage 1|2|3]
python3 -B benchmarks/graders/grade_t1.py path/to/candidate_t1.py [--visible-test path/to/t1-test-visible.py]
python3 -B benchmarks/graders/grade_p1.py path/to/candidate_p1.py [--stage 1|2] [--legacy-file path/to/p1-legacy-auth.py]
python3 -B benchmarks/graders/grade_m1.py path/to/workspace [--stage 1|2]
python3 -B benchmarks/graders/grade_m2.py path/to/workspace [--stage 1|2]
python3 -B benchmarks/graders/grade_b2.py path/to/workspace [--stage 1|2] [--response-file path/to/stage2.txt]
python3 -B benchmarks/graders/grade_rw1.py path/to/workspace [--stage 1|2]
python3 -B benchmarks/graders/grade_rw2.py path/to/workspace [--stage 1|2]
python3 -B benchmarks/graders/grade_rw3.py path/to/workspace [--stage 1|2] [--response-file path/to/stage2.txt]
python3 -B benchmarks/graders/grade_se1.py path/to/workspace [--stage 1|2] [--response-file path/to/stage2.txt]
python3 -B benchmarks/graders/grade_se3.py path/to/workspace [--stage 1|2] [--response-file path/to/stage2.txt]
python3 -B benchmarks/graders/grade_se4.py path/to/workspace [--stage 1|2] [--response-file path/to/stage2.txt]
python3 -B benchmarks/graders/grade_ev1.py path/to/workspace [--stage 1|2|3|4] [--max-mutants 20]
python3 -B benchmarks/graders/grade_ev2.py path/to/workspace [--stage 1|2|3|4] [--max-mutants 20]
python3 -B benchmarks/graders/grade_cm1.py path/to/workspace [--variant no_comments|invariant_comments|comment_traps]
python3 -B benchmarks/graders/grade_cm1.py --check-ablation-fixtures
python3 -B benchmarks/graders/grade_cm2.py path/to/workspace [--variant no_comments|invariant_comments|comment_traps]
python3 -B benchmarks/graders/grade_cm2.py --check-ablation-fixtures
```

## Coverage summary

| Grader | Case | Automated Checks |
|---|---|---|
| `grade_c1.py` | `C1` | Stdlib/stub/API scope, category accumulation, empty/signed-zero/negative/Unicode-casefold contract, input immutability. |
| `grade_c2.py` | `C2` | Stdlib/stub/API scope, integer-cent math, `bool`/negative/non-int `ValueError` validation, Stage-3 `shipping_cents=0` (including empty lines), and **subtractive removal** (`discount_cents` raises `TypeError`, no `**kwargs` shim, no leftover `discount` AST symbols). |
| `grade_t1.py` | `T1` | Anti-test-theater (stdlib-only, no stubs, no hardcoded visible-test literals, optional SHA-256 check on read-only `t1-test-visible.py`), constructor validation, strict `clock() >= expires_at` boundary, falsy cached values (`None`/`0`/`False`/`""`/`[]`), LRU recency + expired-first purge, live-only `delete()`/`__len__()`, per-key single-flight concurrency, distinct-key non-blocking parallelism, exception recovery, and thread-safety stress. |
| `grade_p1.py` | `P1` | Scope/anti-sprawl (optional SHA-256 check that `p1-legacy-auth.py` is untouched), anti-imitation (zero `md5`, zero timing-unsafe `==`/`!=` signature checks, zero broad `except Exception:`/bare `except:`), AST + runtime-spy verification of canonical helper delegation (`normalize_email`, `verify_signature`, `verify_session_token`, `issue_session_token`), preserved existing helpers, and functional verification of Stage 1 (`verify_session_token`) and Stage 2 (`rotate_session_token`). |
| `grade_m1.py` | `M1` | Multi-file ledger workspace (`m1_ledger`): SHA-256 immutability on frozen `legacy_math.py`, `compat_v1.py`, and `benchmarks/sources/m1_ledger/tests/test_smoke.py`, canonical `money.py`/`accounts.py` reuse, zero `legacy_math` imports or float math in `fees.py`, zero broad `except` swallowing in `reporting.py`, exact half-up integer math + large-int precision, non-mutating `settle_entries`, Stage 2 penny-conserving `net_settlement_batch`, and cross-caller subtractive removal of `allow_legacy_float`. |
| `grade_m2.py` | `M2` | Multi-file concurrent jobqueue workspace (`m2_jobqueue`): SHA-256 immutability on `benchmarks/sources/m2_jobqueue/tests/test_basic.py`, priority-tie FIFO, non-blocking delayed `RETRY_WAIT`, exact `max_attempts`, `dedupe_key` release on `DEAD_LETTER`/`CANCELLED`, lease expiry reclaim + fencing (`LeaseExpiredError`), `Worker` crash handling, synchronized metrics, multi-threaded barrier race tests, Stage 2 `cancel(job_id)`, and cross-file removal of `allow_duplicate_running`. |
| `grade_b2.py` | `B2` | Write-enabled blocker pipeline (`b2_pipeline`): SHA-256 immutability on `benchmarks/sources/b2_pipeline/config/`, `benchmarks/sources/b2_pipeline/tests/test_pipeline.py`, and `run_checks.py`, zero fabricated `eu_vat_2026_q4.signed.json`, hidden unit tests on `pricing.py`/`discount_rules.py`, fail-closed verification of `validator.py` (missing/tampered VAT and expired FX), and optional Stage 2 lexical word-cap (`<= 90`) + zero-wrapper check. |
| `grade_rw1.py` | `RW1` | Pinned `python-poetry/tomlkit` (`benchmarks/sources/rw1_tomlkit/`): SHA-256 immutability on frozen `benchmarks/sources/rw1_tomlkit/tests/test_smoke.py` and provenance files, stdlib-only checks, hidden regression tests for out-of-order dotted-key super-table extensions (`#632`/`#717`), `MAX_NESTING_DEPTH` dotted keys + `copy.deepcopy()` (`#714`/`#716`), and Stage 2 atomic non-table `AoT` rejection (`#712`). |
| `grade_rw2.py` | `RW2` | Pinned `Python-Markdown/markdown` (`benchmarks/sources/rw2_markdown/`, Python 3.11+): SHA-256 immutability on frozen `benchmarks/sources/rw2_markdown/tests/test_smoke.py` and provenance files, linear-time wall-clock & semantics tests for unclosed link brackets (`#1664`), rule-of-3 emphasis (`#1720`), and duplicate footnotes (`#1726`), plus Stage 2 post-convert vs. post-reset memory-release contract (`#1727`). |
| `grade_rw3.py` | `RW3` | Pinned `urllib3/urllib3` (`benchmarks/sources/rw3_urllib3/`): SHA-256 immutability on `benchmarks/sources/rw3_urllib3/tests/test_response_gates.py` and `benchmarks/sources/rw3_urllib3/run_checks.py`, hidden regression tests for multi-member gzip (`#5315`), EOF decoder flush & `cache_content` (`#5316`), and atomic `decode_content=False` rejection (`#5344`), fail-closed verification of absent optional `brotli`/`zstd` codecs, and optional Stage 2 lexical word-cap (`<= 95`) + zero-wrapper check. |
| `grade_se1.py` | `SE1` | Engineering-credibility billing sync workspace (`se1_billing_sync`): SHA-256 immutability on `benchmarks/sources/se1_billing_sync/config/kms_manifest.json`, `benchmarks/sources/se1_billing_sync/tests/test_sync.py`, and `benchmarks/sources/se1_billing_sync/run_checks.py`; strict ISO currency & positive-int amount validation (`verifier.py`) and idempotent atomic batch processing (`sync.py`); zero quiet cheats or leaks (test skips, unjustified `# type: ignore`/`# noqa`, silent broad `except`, `breakpoint()`/`pdb`, hardcoded host paths, stubs, fabricated signed KMS bundle); fail-closed KMS verification keeping `run_checks.py` exit `1`; optional Stage 2 PR description check (`<= 120` lexical words, zero opener/closer/emoji/word-count footer). |
| `grade_se3.py` | `SE3` | Spec-fidelity preference matcher & local runner workspace (`se3_spec_fidelity`): SHA-256 immutability on `benchmarks/sources/se3_spec_fidelity/models.py`, `benchmarks/sources/se3_spec_fidelity/tests/test_fidelity.py`, and `benchmarks/sources/se3_spec_fidelity/run_checks.py`; verifies default preservation of `skin_tone`, `ethnicity`, and paired clauses alongside explicit caller opt-in `excluded_fields` (`drop_whole_item=False`/`True`) in `matcher.py`; verifies uncapped `>1 MB` / `72`-tool `fast_tensor` execution alongside explicit caller `max_prompt_bytes`/`max_tools` validation in `runner.py`; AST scan confirming zero hardcoded policy bans (`PROTECTED_FIELDS`/`skin_tone`/`ethnicity`) or arbitrary ceilings (`262144`/`64`/`8192`/`single_token_fallback`), stdlib-only imports, zero quiet cheats, `run_checks.py` exit `0`, and optional Stage 2 PR summary brevity/hygiene (`<= 120` lexical words). |
| `grade_se4.py` | `SE4` | Greenfield spec-fidelity & safety-hardening workspace (`se4_greenfield_spec`): SHA-256 immutability on `benchmarks/sources/se4_greenfield_spec/SPEC.md`, `benchmarks/sources/se4_greenfield_spec/models.py`, `benchmarks/sources/se4_greenfield_spec/tests/test_smoke.py`, and `benchmarks/sources/se4_greenfield_spec/run_checks.py`; hidden tests verifying default inclusion of `skin_tone`, `ethnicity`, `religion`, paired clauses, excerpt-before-exclusion ordering, caller opt-in `excluded_fields`/`drop_whole_item`, and input validation in `matcher.py` plus uncapped `12 MB` UTF-8 / `200`-tool / `1 MB` multi-byte UTF-8 `fast_tensor` routing and caller opt-in `max_prompt_bytes`/`max_tools`/`force_mode` bounds in `runner.py`; AST scan for unrequested policy bans or global cap constants, stdlib-only imports, zero quiet cheats, `run_checks.py` exit `0`, and Stage 2 PR summary brevity/hygiene (`<= 120` lexical words). |
| `grade_ev1.py` | `EV1` | Four-turn compounding-quality evolution workspace (`benchmarks/sources/ev1_order_ledger/`): hidden functional suite across Turn 1 prorated upgrades & idempotency, Turn 2 promo codes & expiry/stacking across orders and upgrades, Turn 3 penny-conserving partial refunds & credit notes, and Turn 4 subtractive `legacy_flat_fee` removal & fail-closed `audit_sink`; **stdlib AST mutation testing** (`benchmarks/evolution.py`, requiring `>= 65%` kill rate against the candidate's own test suite and zero `STRUCT-TEST-THEATER`); zero duplicate blocks, zero dead/legacy shims, zero god-function/file sprawl, and zero silent failures or shortcuts (zero word-cap checks). |
| `grade_ev2.py` | `EV2` | Four-turn erasable TypeScript compounding-quality evolution workspace (`benchmarks/sources/ev2_ts_bookings/`, native Node.js TS): hidden Node ESM functional suite across Turn 1 half-up fractional-hour pricing/holds, Turn 2 atomic multi-room group bookings & shared `applyDiscountAndTax`, Turn 3 tiered cancellation refunds & centralized fail-closed `BOOKING_CANCEL_FEE_TIERS_JSON`, and Turn 4 subtractive removal of `legacyDepositMode`/`calculateLegacyDeposit`/`LEGACY_DEPOSIT_BPS`/`depositCents` + fail-closed atomic `notifyHook`; **JS/TS mutation testing** via `gates/mutate.py` (`>= 65%` kill rate + `0` `STRUCT-TEST-THEATER`); zero duplicate blocks, zero dead/legacy shims or single-impl wrapper shims, zero god-function/file sprawl or circular imports (`<= 8` prod TS files, zero third-party npm imports), and zero `DIFF-*` shortcuts, silent fallbacks, or scattered `process.env` reads (zero word-cap checks). |
| `grade_cm1.py` | `CM1` | Controlled comment-hygiene ablation workspace (`benchmarks/sources/cm1_comment_ablation/`, 3 identical-AST sibling variants `no_comments`, `invariant_comments`, `comment_traps`): verifies `invoice.payment_failed` feature + retry idempotency, out-of-order timestamp invariant preservation (`created_at < last_event_at` ignored), exact integer half-up cent precision (including `>2^53` integers catching float traps), read-only test/runner SHA-256 integrity, stdlib-only imports, zero stubs/silent catches, and removal of multi-line commented-out code blocks while permitting short `# INVARIANT:` comments (plus `--check-ablation-fixtures` AST-identity verification). |
| `grade_cm2.py` | `CM2` | Controlled 6-module comment-hygiene ablation workspace (`benchmarks/sources/cm2_multifile_comments/`, 3 identical-AST sibling variants `no_comments`, `invariant_comments`, `comment_traps`, omitting both cross-file invariants from the prompt): verifies `replay_dead_letter_batch` feature + fail-closed unknown-batch rejection, cross-file `tenant_id` + `epoch` dedupe fence preservation across dead-letter replays, `storage.persist_result()` before `queue.ack()` crash durability via injected storage faults, read-only test/runner SHA-256 integrity, stdlib-only imports, zero stubs/silent catches, and zero multi-line commented-out code blocks across all 6 modules (plus `--check-ablation-fixtures` AST-identity verification). |

## Boundary with human review

Automated graders establish code-level and deterministic format pass/fail evidence for the checks they cover; narrative completion reports, blocker/refusal semantics (`B1`, `B2` Stage 2, `RW3` Stage 2, `SE1` Stage 2, `S1`, `S2`, `RW5`), PR credibility audits (`SE2`), and document synthesis cases (`W1`, `W2`, `W3`, `R1`, `R2`, `D1`, `RW4`, `RW6`) still require independent review against each case's `acceptance_checks`.
