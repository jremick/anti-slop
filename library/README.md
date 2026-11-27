# Optional Rule Library

`anti-slop` keeps its default rules intentionally small so teams get high-signal protection without false-positive noise or prompt bloat.

This directory documents three things in one machine-readable catalog ([library/catalog.json](catalog.json)):

1. **Default Core:** What runs out of the box and why each layer earned a default spot.
2. **Optional Packs (`OPT-*`):** Curated opt-in deterministic checks and short prompt rules you can enable selectively via `anti-slop-learn library`.
3. **Deliberately Excluded (`EXCL-*`):** Popular rules we evaluated and left out of defaults, with evidence and what we use instead.

---

## Quick CLI Usage

Inspect and enable optional packs without editing JSON by hand:

```bash
# 1. Browse available optional packs and rules
anti-slop-learn library list

# 2. Inspect examples, valid neighbouring cases, why it is optional, and evidence status
anti-slop-learn library show network-timeouts
anti-slop-learn library show OPT-SEC-01

# 3. Preview 3-way verification against your repo without writing to disk
anti-slop-learn library enable network-timeouts --by <your-name> --dry-run

# 4. Import, verify (bad case + valid neighbour + repo scan), and approve into .anti-slop/learned/rules.json
anti-slop-learn library enable network-timeouts --by <your-name>
```

Every `library enable` call runs the full 3-way `verify_rule()` gate from `gates/learn.py`:

1. Must catch the rule's `bad_example`.
2. Must produce `0` hits on its `valid_neighbouring_case`.
3. Must stay within `--max-repo-hits` (default `0`) across your repository's existing non-test files.

Verification is never bypassed. If an optional rule hits existing lines in your repository, `library enable` exits `1`, prints the exact `file:line` matches, and leaves `<repo>/.anti-slop/learned/rules.json` unmodified so you can clean those lines first, enable a single rule ID, or pass an explicit `--max-repo-hits N`.

For approved `prompt_rule` entries, run `anti-slop-learn export-prompt` to render them cleanly outside `standard/core.md`.

---

## 1. What the Default Core Covers (and Why)

Default checks pass three criteria: **high AI frequency**, **low false-positive rate**, and **compounding multi-turn risk**.

| Layer | Location | Default scope | Why it is default |
|---|---|---|---|
| Layer A: Diff & prose gate | `gates/diff_check.py` | 15 `DIFF-*` checks (test skips, unauthorized `tests/` edits, stubs, blanket suppressions, silent catches, debug leftovers, hardcoded host paths, broken Markdown paths, chatbot wrappers, diff budgets) | Objective, zero-token deterministic checks that stop immediate shortcuts and reward hacking (`RW3` test tampering fell from `8/11` to `0/23` in `pilot-3way-v0.6.0`). |
| Layer B: Structural & architectural compounding gate | `gates/structural.py`, `gates/architecture.py` | 11 warning-first `STRUCT-*` / `ARCH-*` checks (`STRUCT-TEST-THEATER`, `STRUCT-SILENT-FALLBACK`, `STRUCT-DUPLICATE-BLOCK`, `STRUCT-DEAD-COMPAT`, `STRUCT-COMMENTED-CODE`, `STRUCT-GOD-FUNCTION`, `STRUCT-GOD-FILE`, `STRUCT-SCOPE-SPRAWL`, `ARCH-CIRCULAR-IMPORT`, `ARCH-SINGLE-IMPL-WRAPPER`, `ARCH-BOUNDARY-SCATTER`) | Catches patterns that pass quick smoke runs but poison later AI turns (warning-first by default; blocking with `--strict-structural`). |
| Standing core standard | `standard/core.md` | 7 stable rules (`R1`-`R7`), pinned at `0.2.0` (`<= 300` words) | Keeps universal behavioral expectations compact; model-specific adjustments live separately in `gates/model_deltas.json`. |

---

## 2. Curated Optional Packs (`OPT-*`)

Each optional rule declares its prevention layer, evidence status (`External empirical study`, `Local measured`, or `Practitioner hypothesis`), valid neighbouring case, and retirement trigger in `library/catalog.json`.

| Pack ID | Rule IDs | Layer | Severity | What it guards | Evidence status |
|---|---|---|---|---|---|
| `network-timeouts` | `OPT-NET-01`, `OPT-NET-02` | `deterministic_check` | `warning` | Python `requests.*` / `urllib.request.urlopen` calls without `timeout=`, and JS/TS `fetch()` without `signal:` timeout wiring | `Practitioner hypothesis` |
| `security-boundaries` | `OPT-SEC-01`, `OPT-SEC-02`, `OPT-SEC-03` | `deterministic_check` | `error` | Python `subprocess.*(..., shell=True)`, unsafe `yaml.load()` without `SafeLoader`, and dynamic `eval()` / `exec()` in non-test code | `External empirical study` |
| `comment-hygiene` | `OPT-CMT-01` | `prompt_rule` (`40w`) | `warning` | Delete dead commented-out code and narrating/stale comments; keep only brief non-obvious "why / invariant" comments (paired with `STRUCT-COMMENTED-CODE`) | `External empirical study` |
| `verification-proof` | `OPT-VER-01` | `prompt_rule` (`39w`) | `warning` | Require live end-to-end or real-artifact verification output before claiming completion on apps, APIs, or CLIs instead of mock-only unit tests | `External empirical study` |
| `build-config-hygiene` | `OPT-CFG-01`, `OPT-CFG-02` | `deterministic_check` | `warning` / `error` | Floating `FROM ...:latest` tags in Dockerfiles and world-writable `chmod 777` / `0o777` permissions | `Practitioner hypothesis` |
| `architecture-simplicity` | `OPT-ARC-01` | `prompt_rule` (`33w`) | `warning` | Avoid single-implementation factory, interface, and DI wrapper layers until a second concrete implementation exists | `Practitioner hypothesis` |

### Why these packs are optional

- **`network-timeouts`:** Internal scripts or centralized HTTP clients may configure timeouts at the session/adapter layer rather than on every call site.
- **`security-boundaries`:** High-confidence diff guards complementary to full CI SAST; some CLI wrappers or code generators legitimately invoke shells or `exec()`.
- **`comment-hygiene`:** Paired with deterministic `STRUCT-COMMENTED-CODE`; kept out of `standard/core.md` while controlled multi-model ablation (`benchmarks/cases/CM1.json`, `benchmarks/graders/grade_cm1.py`) tests whether the prompt rule adds value beyond deterministic removal.
- **`verification-proof`:** Valuable for runnable apps, APIs, and CLIs, but pure algorithm libraries or air-gapped sandboxes may not have live endpoints.
- **`build-config-hygiene`:** Useful for containerized production services; not every repository ships Dockerfiles or shell deployment scripts.
- **`architecture-simplicity`:** Explicit practitioner hypothesis; plugin frameworks and multi-backend SDKs may legitimately define interfaces upfront.

---

## 3. Considered and Deliberately Excluded (`EXCL-*`)

These ideas were evaluated and intentionally kept **out** of the default core:

| ID | Considered rule | Why excluded | Evidence | What `anti-slop` does instead |
|---|---|---|---|---|
| `EXCL-01` | Statistical AI-text / "slop" detectors as CI blockers | High false positives, especially on non-native English writing (`61.22%` FP in Liang et al.). | `docs/evidence.md` (`EXT-13`) | Objective deterministic diff/doc checks and warning-first prose patterns. |
| `EXCL-02` | Unfiltered SAST rulesets as blocking post-edit hooks | Default Semgrep/CodeQL rules matched human ground truth on only `65%` / `61%` of 1,080 LLM samples (Firouzi & Ghafari), causing noisy churn. | `docs/evidence.md` (`EXT-13`) | Run full SAST in CI security lanes; offer narrow opt-in `security-boundaries` diff guards. |
| `EXCL-03` | Blanket "delete all comments" policies | ICPC 2026 automated bug-fixing ablation showed indiscriminate comment removal hurts bug fixing when useful intent/invariant comments vanish. | `docs/evidence.md` (`EXT-14`) | Catch commented-out code deterministically (`STRUCT-COMMENTED-CODE`), keep brief invariant comments, and test via `CM1`. |
| `EXCL-04` | Blanket "be concise" / "keep it short" standing prompts | GPT-6.2 vendor guidance warns brevity prompts strip uncertainty caveats, and rigid style rules make Fable 5.2 prose choppy. | `docs/evidence.md` (`OAI-02`, `ANT-04`, `EXT-06`) | Keep `standard/core.md` (`R5`) focused on cutting filler while preserving caveats; isolate measured deltas in `gates/model_deltas.json`. |
| `EXCL-05` | 100% line-coverage mandates as an AI gate | Incentivizes assertion-free and heavily mocked test theater (`36%` vs `26%` mock rate in Hora & Robbes). | `docs/evidence.md` (`EXT-13`) | Flag `STRUCT-TEST-THEATER` and run diff-scoped AST mutation testing (`anti-slop-mutate` and `benchmarks/evolution.py`). |
| `EXCL-06` | Heavyweight upfront DI / single-implementation abstractions | Splits trivial logic across multiple files, burning agent context and encouraging duplicate helpers. | `docs/ai-era-rules.md` | Prefer direct modules by default (`R3`) and offer opt-in `OPT-ARC-01` (`architecture-simplicity`). |

---

## Validation Contract

`scripts/check.py` automatically validates `library/catalog.json` on every test run:

- Schema version, unique IDs across `OPT-*` and `EXCL-*`, and valid `evidence_status` labels.
- Every deterministic `OPT-*` rule compiles cleanly, catches its own `bad_example`, and produces `0` hits on its `valid_neighbouring_case`.
- Every `prompt_rule` entry stays `<= 45` words and includes non-empty `why_not_deterministic` and `retirement_trigger` fields.
