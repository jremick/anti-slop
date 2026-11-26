# Layer-1 Deterministic Gates (`gates/`)

Opt-in runtime and CI checks that enforce mechanical anti-slop invariants outside `standard/core.md` at zero standing-prompt token cost.

Every Python gate uses stdlib Python only (no third-party packages), exits `0` silently on pass, and emits structured findings with remediation guidance on failure (`exit 1`).

## Contents

- [api_checks.py](api_checks.py): Validates 2026 model API and harness configurations (`anti-slop-api`) for `gpt-6.2-astra`, `gpt-6.2-sol`, `claude-opus-5-5`, `claude-fable-5-2`, and `gemini-4-neon`.
- [diff_check.py](diff_check.py): Validates unified diffs, modified file lists, and PR bodies (`anti-slop-diff`) for stub additions, unauthorized edits under `tests/`, newly added test-skip/waiver annotations (`DIFF-TEST-SKIP`), unjustified lint/type suppressions (`DIFF-SUPPRESSION`), silent broad catches (`DIFF-SILENT-CATCH`), debug leftovers (`DIFF-DEBUG-LEFTOVER`), hardcoded host home paths (`DIFF-HOST-PATH`), optional net-LOC and file-count budgets (`--no-budget` to disable), chatbot openers and closers (`DIFF-CHATBOT-OPENER`, `DIFF-CHATBOT-CLOSER`), decorative AI emojis (`DIFF-DECORATIVE-EMOJI`, warning by default), and broken backticked local repo paths.
- [hooks/](hooks/README.md): Portable 3-CLI lifecycle hooks (`anti-slop-hook`, including `--install claude|antigravity|codex --dry-run`) wrapping `gates/diff_check.py` outside the model context window.
- [model_deltas.json](model_deltas.json): Strictly delta-only per-model harness overlays (`D-AST`, `D-SOL`, `D-OPU`, `D-FAB`, `D-NEO`) with stable IDs, falsification checks, valid neighbouring cases, and effort routing. Keep outside `standard/core.md`.
- [vale/.vale.ini](vale/.vale.ini): Warning-first Vale configuration implementing the deterministic subset of Cursor `unslop` across [Openers.yml](vale/styles/AntiSlop/Openers.yml), [Closers.yml](vale/styles/AntiSlop/Closers.yml), [ADRStructure.yml](vale/styles/AntiSlop/ADRStructure.yml), [Vocab.yml](vale/styles/AntiSlop/Vocab.yml), and [Phrasing.yml](vale/styles/AntiSlop/Phrasing.yml).
- [ci-ratchet.yml](ci-ratchet.yml): Opt-in GitHub Actions workflow template showcasing the reusable composite action (`action.yml` / `uses: jremick/anti-slop@v0.6.0`), `uvx`, and vendored script execution across four independent modular jobs (`diff-gate`, `api-config-gate`, `code-hygiene-ratchet`, `prose-vale-ratchet`).

## Quick Usage

### 1. Run in Any External Repository (Zero-Clone `uvx`, Action, or `pre-commit`)

`pyproject.toml` exposes three zero-dependency console scripts (`anti-slop-diff`, `anti-slop-hook`, `anti-slop-api`), while root `action.yml` and `.pre-commit-hooks.yaml` enable drop-in CI and local hooks without copying `gates/`:

```bash
# Run on your current git diff (objective defects only, no LOC/file caps)
git diff HEAD | uvx --from git+https://github.com/jremick/anti-slop anti-slop-diff --diff - --no-budget

# Validate a model/harness JSON config
uvx --from git+https://github.com/jremick/anti-slop anti-slop-api path/to/model-config.json

# Install user-level hooks for Claude Code, Antigravity, or Codex (preview first with --dry-run)
uvx --from git+https://github.com/jremick/anti-slop anti-slop-hook --install claude --dry-run
```

GitHub Actions (5-line drop-in via `action.yml`):

```yaml
- uses: jremick/anti-slop@v0.6.0
  with:
    no-budget: 'true'
```

Local `pre-commit` (via `.pre-commit-hooks.yaml`):

```yaml
repos:
  - repo: https://github.com/jremick/anti-slop
    rev: v0.6.0
    hooks:
      - id: anti-slop-diff
```

### 2. Validate Model API and Harness Configs

```bash
python3 -B gates/api_checks.py path/to/model-config.json
python3 -B gates/api_checks.py --json --strict path/to/neon-config.json
```

Returns `{ok, model, errors, warnings}` in `--json` mode and exits `1` on any `error` or `critical` finding (such as a `claude-fable-5-2` silent downgrade via `model_refusal_fallback` to `claude-opus-4-8` or `claude-opus-5`).

### 3. Validate Diffs, Files, and PR Descriptions

```bash
git diff origin/main...HEAD | python3 -B gates/diff_check.py --diff - --repo-root . --no-budget
python3 -B gates/diff_check.py --files docs/models.md gates/README.md --repo-root .
python3 -B gates/diff_check.py --diff pr.diff --allow-test-edit --max-net-loc 400 --max-files 10 --json
python3 -B gates/diff_check.py --diff pr.diff --allow-test-edit --allow-test-skip --strict-prose --json
```

Starting budgets (`--max-net-loc 400`, `--max-files 10`, PR comment cap `<= 10`, Fable `concurrent_subagents <= 3`, Neon thinking ratio `<= 4:1`, Neon TTFT `<= 45s`) are `[Heuristic]` defaults to calibrate locally against repository telemetry. Pass `--no-budget` on first-time adoption to enforce only zero-FP objective defects without hitting the default LOC/file caps.

Engineering-credibility checks in `gates/diff_check.py`:

- `DIFF-TEST-SKIP` (`error`): Blocks newly added test-skip/waiver annotations (`@unittest.skip`, `@unittest.skipIf`, `@unittest.skipUnless`, `@pytest.mark.skip`, `@pytest.mark.skipif`, `@pytest.mark.xfail`, `self.skipTest(`, `pytest.skip(`, `it.skip(`, `test.skip(`, `describe.skip(`, `xit(`, `xtest(`) even when `--allow-test-edit` is set; override only with explicit `--allow-test-skip`.
- `DIFF-SUPPRESSION` (`error`): Flags newly added unjustified lint/type suppressions (bare `# type: ignore` without `[code]` + reason, bare `# noqa` without specific rule code, `@ts-ignore`, bare `@ts-expect-error` without explanation, bare `eslint-disable`/`eslint-disable-next-line` without specific rule + `-- reason`, bare `// nolint` without linter name + reason). Valid scoped suppressions (e.g., `# noqa: E402`, `# type: ignore[arg-type]  # upstream stub`, `// @ts-expect-error -- legacy CJS interop`, `// eslint-disable-next-line no-console -- CLI output`) pass cleanly.
- `DIFF-SILENT-CATCH` (`error`): Flags newly added Python bare `except:` or broad `except Exception:` / `except BaseException:` handlers whose body only executes `pass`, `...`, or returns `None`/`[]`/`{}`/`False` with no logging or re-raise, plus empty JS/TS `catch (...) {}` blocks. Narrowed exceptions (e.g., `except ProcessLookupError: pass`) and handlers that log or re-raise pass cleanly.
- `DIFF-DEBUG-LEFTOVER` (`error`): Flags newly added `breakpoint()`, `pdb.set_trace()`, `ipdb.set_trace()`, and JS/TS `debugger;` statements outside strings and comments.
- `DIFF-HOST-PATH` (`error`): Flags newly added hardcoded local home paths matching real usernames (`/Users/<user>/`, `/home/<user>/`, `C:\Users\<user>\`) in code or Markdown while allowing explicit placeholders (`/Users/...`, `/Users/<user>/`, `/Users/example/`, `<HOME>`, `<REPO_ROOT>`).
- `DIFF-CHATBOT-CLOSER` (`error`): Flags trailing chatbot closing filler (`Let me know if you'd like...`, `Hope this helps`, `Feel free to reach out`, `Happy to adjust/help if`) in Markdown docs and PR bodies (mirrored in `gates/vale/styles/AntiSlop/Closers.yml`).
- `DIFF-DECORATIVE-EMOJI` (`warning`, or `error` with `--strict-prose`): Flags decorative AI emojis outside fenced code blocks and inline code spans.

Reusable Python helpers exported by `gates/diff_check.py` for graders and tooling include `check_credibility_text(...)`, `check_diff_and_text(...)`, `check_markdown_openers(...)`, `check_markdown_closers(...)`, `check_decorative_emojis(...)`, `check_host_paths(...)`, `check_test_skips_in_source(...)`, `check_suppressions_in_source(...)`, `check_silent_catches_in_source(...)`, and `check_debug_leftovers_in_source(...)`.

### 4. Benchmark `core-rules` vs. `model-controls`

Load `standard/core.md` alone for the `core-rules` condition. For `model-controls`, load `standard/core.md` plus ONLY the single matching model block from `gates/model_deltas.json`. Never paste model deltas into `standard/core.md`; retire obsolete `D-*` rules by leaving a numeric gap.

## Incremental Adoption

Adopt gates one job at a time rather than enabling a full linter stack on Day 1:

1. **Start with zero-dependency gates:** Enable `diff-gate` (via `uses: jremick/anti-slop@v0.6.0` with `no-budget: 'true'`) and `api-config-gate` from `gates/ci-ratchet.yml`. These require only Python stdlib and catch objective failures (HTTP 400 API traps, silent Fable downgrades, stub placeholders, unauthorized test edits, test-skip waivers, unjustified suppressions, silent broad catches, debug leftovers, hardcoded host paths, chatbot openers/closers, broken local doc paths).
2. **Add warning-first prose checks:** Enable `prose-vale-ratchet` on changed Markdown files. Only `AntiSlop.Openers` and `AntiSlop.Closers` block by default (`level: error`). `AntiSlop.Vocab`, `AntiSlop.Phrasing`, `AntiSlop.ADRStructure`, and `DIFF-DECORATIVE-EMOJI` default to `warning`.
3. **Layer stack-specific code ratchets:** Enable only the `code-hygiene-ratchet` tools matching your stack (`ruff`/`vulture` for Python, `knip` for JS/TS, `jscpd` for duplicate blocks) scoped strictly to changed files so legacy debt does not block active PRs.

## Warning-First Calibration and Anti-Overcorrection

Follow the prose boundaries in [docs/operating-guide.md](../docs/operating-guide.md):

- **Never treat style warnings as proof of factual error.** Reserve hard CI errors for objective defects (broken paths, chatbot openers/closers, API contract traps, unauthorized test edits, test-skip waivers, unjustified suppressions, silent broad catches, debug leftovers, hardcoded host paths, stub code). Keep decorative emoji checks (`DIFF-DECORATIVE-EMOJI`) at `warning` unless `--strict-prose` is explicitly enabled.
- **Preserve domain vocabulary.** `gates/vale/styles/AntiSlop/Vocab.yml` and `gates/vale/styles/AntiSlop/Phrasing.yml` intentionally omit `vector`, `harness`, `primitive`, `surface`, `substrate`, and `features` from their banned `tokens` and guard them in `exceptions` so future edits do not degrade technical documentation into choppy prose (a documented failure mode under rigid style rules on Claude Fable 5.2).
- **Test valid neighbouring cases before tightening any gate.** Before promoting `ADRStructure` from `warning` to `error` or lowering diff budgets, verify the change against both a reproduced defect and a valid neighbouring case (see [CONTRIBUTING.md](../CONTRIBUTING.md) and [tests/test_gates.py](../tests/test_gates.py)).
