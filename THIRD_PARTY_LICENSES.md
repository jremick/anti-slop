# Third-Party Licenses & Attribution

This repository itself is licensed under the [MIT License](LICENSE) and has **zero third-party runtime dependencies** (stdlib Python >= 3.11 only).

To support deterministic, offline `origin: real_work` benchmark grading, `benchmarks/sources/` includes pinned historical source snapshots from five upstream open-source projects across six benchmark fixtures (`RW1`–`RW6`). These snapshots are test fixtures only and are not packaged into the `anti-slop` Python distribution (`pyproject.toml`). Each snapshot preserves its upstream license text verbatim alongside an `UPSTREAM.json` commit manifest.

## Vendored Benchmark Source Snapshots (`RW1`–`RW6`)

| Fixture | Upstream Project | Pinned Commit / Tag | Upstream License | Redistribution License | Verbatim Notice & Manifest |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `RW1` | [python-poetry/tomlkit](https://github.com/python-poetry/tomlkit) | `7bf7284dbd622557d9909f8fee017a4cb169a139` | MIT | MIT | `benchmarks/sources/rw1_tomlkit/LICENSE`, `benchmarks/sources/rw1_tomlkit/UPSTREAM.json` |
| `RW2` | [Python-Markdown/markdown](https://github.com/Python-Markdown/markdown) | `2c96e36ba4750cf18583d62e2fcecff49e077419` | BSD-3-Clause | BSD-3-Clause | `benchmarks/sources/rw2_markdown/LICENSE.md`, `benchmarks/sources/rw2_markdown/UPSTREAM.json` |
| `RW3` | [urllib3/urllib3](https://github.com/urllib3/urllib3) | `c5347bbd39203d68d7b0e3ffb83ced3e3b4b9109` | MIT | MIT | `benchmarks/sources/rw3_urllib3/LICENSE.txt`, `benchmarks/sources/rw3_urllib3/UPSTREAM.json` |
| `RW4` | [pypa/packaging](https://github.com/pypa/packaging) | `20de131f397a24a2d1723ff90c17f2e5b33d2766` | Apache-2.0 OR BSD-2-Clause | **BSD-2-Clause** (selected) | `benchmarks/sources/rw4_packaging_264/LICENSE`, `benchmarks/sources/rw4_packaging_264/LICENSE.BSD`, `benchmarks/sources/rw4_packaging_264/LICENSE.APACHE`, `benchmarks/sources/rw4_packaging_264/UPSTREAM.json` |
| `RW5` | [andialbrecht/sqlparse](https://github.com/andialbrecht/sqlparse) | `60cdc649726bf1bc4f1b336050560b336da715ec` | BSD-3-Clause | BSD-3-Clause | `benchmarks/sources/rw5_sqlparse/LICENSE`, `benchmarks/sources/rw5_sqlparse/UPSTREAM.json` |
| `RW6` | [python-poetry/tomlkit](https://github.com/python-poetry/tomlkit) | `d2aa305673a01eafd0edda54ef07ebcb8902f4d4` (`0.15.3`) | MIT | MIT | `benchmarks/sources/rw6_tomlkit_release/LICENSE`, `benchmarks/sources/rw6_tomlkit_release/UPSTREAM.json` |

### Notes on Dual-Licensed & Embedded Upstream Files

- **`benchmarks/sources/rw4_packaging_264/` (`pypa/packaging`):** Upstream `pypa/packaging` is dual-licensed under **Apache-2.0 OR BSD-2-Clause** (`benchmarks/sources/rw4_packaging_264/LICENSE`). This repository explicitly selects **BSD-2-Clause** (`benchmarks/sources/rw4_packaging_264/LICENSE.BSD`) for redistributing the renamed benchmark fixture files (`01-*`–`05-*`) to avoid Apache-2.0 §4(b) modification-notice ambiguity, while retaining both `benchmarks/sources/rw4_packaging_264/LICENSE.APACHE` and `benchmarks/sources/rw4_packaging_264/LICENSE.BSD` verbatim.
- **`benchmarks/sources/rw4_packaging_264/05-licenses-init.py` (`pypa/hatch` attribution):** As inherited from upstream `pypa/packaging`, this file includes code adapted from [pypa/hatch](https://github.com/pypa/hatch/blob/5352e44/backend/src/hatchling/licenses/parse.py) under the **MIT License** (Copyright (c) 2017-present Ofek Lev); its verbatim MIT header is preserved at the top of the file.

### Upstream Copyright Summaries

- `python-poetry/tomlkit` (`RW1`, `RW6`): Copyright (c) 2018 Sébastien Eustace (MIT).
- `Python-Markdown/markdown` (`RW2`): Copyright 2007, 2008 The Python Markdown Project; Copyright 2004, 2005, 2006 Yuri Takhteyev; Copyright 2004 Manfred Stienstra (BSD-3-Clause).
- `urllib3/urllib3` (`RW3`): Copyright (c) 2008-2020 Andrey Petrov and contributors (MIT).
- `pypa/packaging` (`RW4`): Copyright (c) Donald Stufft and individual contributors (Apache-2.0 OR BSD-2-Clause; redistributed here under BSD-2-Clause).
- `andialbrecht/sqlparse` (`RW5`): Copyright (c) 2016, Andi Albrecht (BSD-3-Clause).

## Editorial References (Non-Vendored Attribution)

The following external publications informed design choices and warning-first style rules documented in `docs/evidence.md`. No upstream code is vendored from these sources.

- **`REF-01` — [No AI Slop: A Manifesto](https://www.slopmanifesto.com/):** AIE Code Summit contributors (Dex Horthy et al., Nov 2026). Editorial reference supporting outcomes over output, effort-asymmetry framing, stakes-based review, twice-occurring mistake escalation, and deterministic automation.
- **`REF-02` — [Cursor `unslop` skill](https://github.com/cursor/plugins/blob/main/pstack/skills/unslop/SKILL.md):** Cursor plugin repository (Lauren Tan / `poteto`). Editorial reference informing the stable-ID retirement gap contract and the deterministic prose-lint subset adapted into warning-first Vale rules under `gates/vale/` with technical domain allowlists.
