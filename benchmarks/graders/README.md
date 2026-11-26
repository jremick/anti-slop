# Automated Coding Graders

Twelve zero-dependency, stdlib-only Python graders for single-file (`C1`, `C2`, `T1`, `P1`) and multi-file workspace (`M1`, `M2`, `B2`, `RW1`, `RW2`, `RW3`, `SE1`, `EV1`) coding benchmark cases. Each grader runs isolated static (AST/hygiene) and dynamic (contract/hidden-suite or AST mutation) checks and emits deterministic JSON evidence.

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
python3 -B benchmarks/graders/grade_ev1.py path/to/workspace [--stage 1|2|3|4] [--max-mutants 20]
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
| `grade_ev1.py` | `EV1` | Four-turn compounding-quality evolution workspace (`benchmarks/sources/ev1_order_ledger/`): hidden functional suite across Turn 1 prorated upgrades & idempotency, Turn 2 promo codes & expiry/stacking across orders and upgrades, Turn 3 penny-conserving partial refunds & credit notes, and Turn 4 subtractive `legacy_flat_fee` removal & fail-closed `audit_sink`; **stdlib AST mutation testing** (`benchmarks/evolution.py`, requiring `>= 65%` kill rate against the candidate's own test suite and zero `STRUCT-TEST-THEATER`); zero duplicate blocks, zero dead/legacy shims, zero god-function/file sprawl, and zero silent failures or shortcuts (zero word-cap checks). |

## Boundary with human review

Automated graders establish code-level and deterministic format pass/fail evidence for the checks they cover; narrative completion reports, blocker/refusal semantics (`B1`, `B2` Stage 2, `RW3` Stage 2, `SE1` Stage 2, `S1`, `S2`, `RW5`), PR credibility audits (`SE2`), and document synthesis cases (`W1`, `W2`, `W3`, `R1`, `R2`, `D1`, `RW4`, `RW6`) still require independent review against each case's `acceptance_checks`.
