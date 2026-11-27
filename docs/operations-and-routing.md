# Operations, routing and slop-removal playbook

Keep this document **outside** always-loaded standing prompts (`standard/core.md`). It translates the verified findings in [model profiles](models.md) and the [evidence ledger](evidence.md) into operational routing, stakes-tiered verification, safe legacy cleanup and rule-pruning governance.

Every numeric default marked **`[Heuristic]`** is a configurable starting point to calibrate locally using `benchmarks/` and live telemetry—never an empirical constant.

---

## Cross-Model Polarities & Workload Routing Playbook

Late-2026 frontier models fail in **opposing directions** (`models.md`): blanket prompts such as *"be concise"* strip caveats on GPT-6.2 Astra/Sol (`OAI-02`, `EXT-06`), while raising reasoning effort lowers quality or precision on Fable 5.2 `max` (`EXT-09`), GPT-6.2 Sol `high` (`EXT-05`), and Gemini 4 Neon `xhigh` (`EXT-02`, `EXT-06`). Route workloads to model strengths and isolate per-model adjustments inside `gates/model_deltas.json` and `gates/api_checks.py`.

| Workload | Primary Model & Effort | Cross-Family Verifier | Rationale (`[Tier A]` Evidence) |
|---|---|---|---|
| **Routine bug fixes, CLI work & automated PR review** | **GPT-6.2 Sol** (`low`/`medium`) or **Claude Opus 5.5** (`medium` single-pass; `high` multi-file) | Cross-vendor review (`Opus 5.5` ↔ `Sol` or `Neon HIGH` w/ `response_schema`) | Sol ties Astra on Terminal-Bench (61.5%, `EXT-09`) and leads CodeRabbit precision at `low` (32.7%, 11 nitpicks vs. 33 at `high`, `EXT-05`) at 1/4 token cost; Opus 5.5 sits on the cost-intelligence Pareto frontier (`EXT-02`). |
| **Hard multi-file architecture & scientific/math specs** | **Claude Fable 5.2** (`high`/`xhigh`; never `max` in loops) or **GPT-6.2 Astra** (`high`/`max` for scientific CLI) | **Astra** ↔ **Fable 5.2** / **Neon** (never same vendor family) | Fable leads FrontierSWE v2 (69.9%, `EXT-03`) and AA-Omniscience acc (~79.1%, `EXT-06`); Astra leads Agents' Last Exam & Terminal-Bench-Science (`OAI-01`). Hand mechanical multi-file edits to Opus 5.5 or Sol (`EXT-09`). |
| **Orchestrated tool workflows, multimodal & 1M recall** | **Gemini 4 Neon** (`HIGH` inside a bounded harness; delegate routine edits to `gemini-4-hydrogen`) | **Opus 5.5** (`high`) or **Sol** (`low`/`medium`) | Neon leads LiveBench 2.0 (87.4), AA Coding Agent (58.6), GraphWalks 1M (95.2%) and #2 steerability (`GOO-01`, `GOO-03`, `EXT-10`). Bounded harnesses avoid the 3× SWE-sweep drop (`GOO-01`). |
| **Security, auth & infrastructure changes** | **Claude Opus 5.5** (`high`/`xhigh`) or **Gemini 4 Neon** (`HIGH` + cached current SDK docs + adversarial schema) | Cross-family adversarial reviewer + deterministic SAST (`Semgrep`) | Avoids Fable 5.2's sticky Opus 4.8 cyber fallback (`ANT-05`) and GPT-6.2's Critical-tier refusal/stub friction (`OAI-01`, `EXT-10`). |
| **ML training, local inference engines & sensitive-attribute business logic** | **Gemini 4 Neon** (`HIGH`) or **GPT-6.2 Astra** (`medium`/`high`); bound Claude to narrow, spec-locked sub-tasks with `D-OPU-5` / `D-FAB-4` | Mandatory clean-room cross-family `anti-slop audit` + locked Tier-1 `anti-slop verify` metric/contract assertions | Avoids Anthropic system-card frontier AI R&D training-time capability caps, sticky dual-use fallbacks (`ANT-05`), and unrequested policy-laundering / hardcoded ceiling drift (`SE3`, `HARNESS-SAME-FAMILY-AUDIT`, `CLAUDE-ML-RD-CAP-WARNING`). |
| **Technical prose, RFCs & decision memos** | **Opus 5.5** (`medium`/`high`) or **Neon** (`MEDIUM`/`HIGH`) + warning-first `gates/vale/` | Cross-family epistemic auditor (`Fable 5.2` / `Neon` / `Astra` + source check) | Avoids GPT-6.2's 55%–59% wrong/unknown hallucination and stripped-caveat compression (`EXT-06`) unless strictly grounded via `R2` + `D-AST-1`/`D-SOL-1`. |

---

## 4-Tier Stakes Review Matrix

Operationalizes the Slop Manifesto's stakes-based review principle (`REF-01`) with explicit mechanical and human verification floors:

| Stakes Tier | Artifact Examples | Mandatory Automated Checks (`gates/` + Tests) | Independent Verifier & Human Review |
|---|---|---|---|
| **Tier 0: Disposable** | Throwaway scripts, local spikes, brainstorm notes | `gates/api_checks.py`; label `DISPOSABLE — DO NOT MERGE`. | None; blocked from merging into main repo or shared docs. |
| **Tier 1: Routine** | Single-module fixes, doc updates, small utilities (`≤ 150 net LOC` `[Heuristic]`) | `gates/diff_check.py` (stubs, path integrity, opener lint, diff budget) + existing unit tests + read-only `tests/` mount (`--allow-test-edit` required to change tests). | Automated cross-family diff/claim check; spot-check human review (`~10%–20%` sample `[Heuristic]`). |
| **Tier 2: Production / Multi-File** | Feature PRs, multi-module refactors, RFCs/ADRs, user-facing docs | All Tier 1 + clone/dead-code/architecture ratchets (`gates/ci-ratchet.yml`) + mutation testing (`Stryker`/`mutmut`) or property tests on touched critical paths + read-only held-out suite + source/link audit. | Mandatory **clean-room cross-family verifier** (`auditor_provider != generator_provider`) + human review of **plan/design + diff summary + critical invariants**. |
| **Tier 3: High-Stakes / Security / Architecture** | Auth, crypto, billing, migrations, external specs, eval harnesses | All Tier 2 + adversarial security invariant check (`response_schema`) + third-person neutral trade-off audit (`EXT-12`) + calibrated grader check (`EXT-12`). | Mandatory **full human line-by-line review** by domain owner + independent cross-family adversarial audit. |

---

## Cross-Family Verification & Anti-Compounding Circuit Breakers

### Cross-Family Verification Mandate

Two independent 2026 findings rule out same-vendor self-certification on Tier 2–3 work:
1. **Correlated same-vendor judge blind spots:** UK AISI documented OpenAI sibling model-judges systematically missing misalignment and policy violations in GPT-6.2 (`EXT-04`).
2. **Self-output bias & high eval awareness:** Epoch AI documented self-output bias on Fable 5.2 (`EXT-09`), while GPT-6.2 Astra (85%, `EXT-04`), Opus 5.5, and Fable 5.2 (`ANT-05`) all exhibit high evaluation awareness.

**Operational policy:** On Tier 2–3 artifacts, enforce `auditor_provider != generator_provider` (e.g., Anthropic ↔ OpenAI ↔ Google) in a **fresh clean-room context** seeing only the spec, diff/artifact, and tool outputs—never the authoring chat transcript. Run this directly via `anti-slop audit --spec-file <spec> --summary-file <pr-body>` ([gates/audit.py](../gates/audit.py)) and validate multi-model harness configs with `gates/api_checks.py` (`HARNESS-SAME-FAMILY-AUDIT`). For high-stakes design trade-offs, frame the audit in third-person neutral voice without disclosing user preference (SYCON Bench measured up to 63.8% debate sycophancy reduction, `EXT-12`).

### Six Structural Circuit Breakers

Prompt rules alone cannot halt multi-turn degradation (`EXT-07`, `EXT-11`, `EXT-12`). Break compounding loops structurally:

1. **Fresh context boundaries & loop circuit breaker:** Split *Plan*, *Author*, and *Verify* sessions. Hard reset after **2–3 consecutive failed fix/block attempts** `[Heuristic]` (enforced automatically via `anti-slop hook --max-consecutive-blocks 3` and mined in `anti-slop learn mine`), passing only structured state (spec, failing command output, file paths) to avoid premature-anchoring cascades (Laban et al. 39% multi-turn drop, `EXT-11`).
2. **Golden anchors & legacy quarantine:** Point agents to 1–2 blessed reference implementations/docs; exclude legacy sloppy directories from retrieval indexes (`.cursorignore` or explicit `LEGACY—DO NOT IMITATE` headers) to block repo vulnerability/clone imitation (ETH Zurich 25–49pp secure-code drop & 76.5% imitation; CASE-Bench +6.3pp exploitable code from 1 bad exemplar, `EXT-12`).
3. **One-way diff ratchets & churn alarms:** Block new clones (`jscpd`), dead exports (`Knip`/`Vulture`), stubs (`gates/diff_check.py`), and oversized PRs (`≤ 300–400 net LOC` / `≤ 10 files` `[Heuristic]`). Flag files rewritten `> 2×` within 14 days `[Heuristic]` (surfaced automatically as `rapid_churn_files` by `anti-slop learn mine`; GitClear 2-week churn window, `EXT-12`) for human architectural inspection.
4. **Evaluator & contract isolation:** Lock tests, human-owned invariant specs, decision records (`docs/decisions/**`), and `<repo>/.anti-slop/verify.json` recipes via `<repo>/.anti-slop/protected-paths.json` (`DIFF-PROTECTED-PATH`, enforced in `PreToolUse` hooks, `gates/diff_check.py`, and `action.yml`), keeping `benchmarks/graders/` and CI gate configs outside agent write permissions to defeat test tampering and sub-agent policy laundering (SpecBench, ImpossibleBench, `EXT-12`).
5. **5-status provenance on handoffs:** Enforce `docs/operating-guide.md`'s 5-status model (`Supported fact`, `Approved decision`, `Assumption/hypothesis`, `Draft`, `Superseded`) across multi-agent handoffs so unverified summaries never become ground truth (`EXT-12` transmissible reward hacking).
6. **Preserve human-curated golden references:** Curate verified human references rather than overwriting them with unreviewed agent rewrites.

---

## Safe Legacy Slop Removal

Asking an agent to *"clean up tech debt across the repo"* replaces old debt with unreviewable diffs, behavioral regressions and new slop. Clean legacy slop in four ordered steps:

1. **Ratchet First, Sweep Second:** Enable diff-scoped gates (`gates/ci-ratchet.yml`, `gates/diff_check.py`, `golangci-lint --new-from-rev`, `ESLint --max-warnings`, `betterer`, diff-scoped `Vale`) before cleaning history so new commits cannot outpace remediation.
2. **Characterization Tests in a Separate Commit:** Before refactoring legacy code, lock observable behavior with characterization/regression tests (and mutation checks on critical paths) in an isolated commit. Never mix feature edits with cleanup diffs.
3. **Single-Invariant Micro-Sweeps ("Garbage Collection"):** Following `OAI-03`, schedule small recurring PRs targeting **one mechanical invariant per PR** (e.g., delete `Knip`/`Vulture`-verified dead code in one module; collapse one `jscpd` clone cluster; prune obsolete branches; strip verified broken links/openers from one doc folder), capped at `≤ 200–300 LOC` `[Heuristic]`.
4. **Deletion-Biased Acceptance Criteria:** Approve a cleanup PR only when target debt measurably falls (net LOC, dead exports, clones or confirmed defects down) at steady or higher test/mutation/claim-verification scores, with zero speculative abstractions added. For documentation or context defects, execute the 5-step downstream supersession repair in [operating-guide.md](operating-guide.md#prevent-errors-from-becoming-authoritative-context).

---

## Golden Eval Ablation and Rule Pruning

Treat `standard/core.md`, `gates/`, and `gates/model_deltas.json` as code subject to regression testing and retirement.

### Triage Before Editing Prompts (4-Bucket Isolation RCA)

When a defect occurs twice (or once if serious), reproduce it in a **fresh context** with a **tightened spec** and **clean golden file**:

| Root-Cause Bucket | Isolation Signal | Smallest Valid Fix |
|---|---|---|
| **A. Missing Deterministic Gate** | Objective invariant CI never checked (stub, API param, dead export, broken path). | Add a check to `gates/` with remediation stderr; add **zero** prompt text. |
| **B. Ambiguous Spec** | Disappears once acceptance criteria, invariants or non-goals are stated. | Fix the task spec template. |
| **C. Polluted Context** | Disappears without sloppy neighbor, stale doc or long history. | Repair/quarantine source context and enforce reset boundaries (`operating-guide.md`). |
| **D. Genuine Model Tendency** | Persists in a clean fresh run with a crisp spec. | Add a paired regression case + **valid neighbouring case** to `benchmarks/cases/`, then test a minimal delta in `gates/model_deltas.json` (only touching `standard/core.md` if cross-model). |

### Scheduled Pruning Cadence *(Monthly or on Major Model/Harness Upgrade `[Heuristic]`)*

1. **Leave-one-out ablation (`scripts/benchmark.py`):** Run the Golden Eval Set (real Stage-1 captures + `benchmarks/cases/`) comparing current rules against an ablated candidate (`--baseline` vs. `--treatment`). **Retire** any rule whose removal shows zero measurable regression (e.g., newer model weights solved it natively) or that has been superseded by a `gates/` check—**leaving its stable ID (`R*` or `D-*`) unused as a permanent gap** while keeping the regression case.
2. **False-positive & bypass audit:** Inspect suppression spikes (`eslint-disable`, `# noqa`, `--no-verify`, manual gate overrides) and valid-neighbouring-case failures. Demote overly noisy prose checks from `error` to `warning` or retire them.
3. **Grader recalibration:** Re-check automated rubric/LLM judges against fresh human binary labels to counter criteria drift (`EXT-12`, Shankar et al.).
