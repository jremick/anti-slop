# Open (Unmerged) Pull Requests on `pypa/packaging` as of 2026-11-25

Captured verbatim from `github.com/pypa/packaging` (`state: open`; NOT merged into commit `20de131f39` / 26.4 notes).

## PR #1585: Fix preferred wheel selection in the tags usage guide
- State: `open` (unmerged; updated `2026-11-25T22:56:41Z`)
- URL: https://github.com/pypa/packaging/pull/1585

Fixes #1584.

The tags usage example breaks only its inner loop after finding a compatible tag. If both a preferred native tag and a later universal tag match, the latter overwrites `best_wheel`. The original doctest has only one match and does not expose this.

Replace that loop with a wheel-selection guide using the existing `create_compatible_tags_selector()` API and real filenames. The doctests cover preferred ordering despite reversed candidate order, compressed tags, incompatible wheels, empty input, and no compatible result. Explicit target tags keep those examples independent of the host platform.

This corrects executable documentation that installer authors may copy; it does not change library behavior.

Validation on Linux / CPython 3.12.14:

- Reproduced the old loop choosing `py3-none-any` over the first supported native tag.
- `python -m pytest -q`: 64,204 passed, 3 skipped, 446 property tests deselected.
- `sphinx-build -W -n -b doctest`: 469 tests passed.
- Strict HTML and LaTeX Sphinx builds passed.
- `pre-commit run --all-files`: all 17 configured hooks passed.
- `git diff --check`: passed.

## PR #1583: Escape backslashes when serializing marker values
- State: `open` (unmerged; updated `2026-11-25T22:02:25Z`)
- URL: https://github.com/pypa/packaging/pull/1583

Fixes #1399.

## Summary

`Value.serialize()` emitted the value verbatim while `process_python_str` interprets backslash escapes through `ast.literal_eval`, so `str(Marker(x))` could re-parse to a marker that evaluates differently:

```python
m = Marker(r'sys_platform == "linu\\x78"')   # two literal backslashes on the wire
m.evaluate({"sys_platform": "linux"})          # False
Marker(str(m)).evaluate({"sys_platform": "linux"})  # True (before this fix)
```

The marker value `linu\x78` (one literal backslash) was written out as `"linu\x78"`, which the next parse reduces to `linux`, flipping the comparison. Since `Metadata.as_rfc822()` stringifies every `Requires-Dist`, one metadata round trip could change whether a dependency is installed.

The fix escapes backslashes during serialization so the emitted literal re-parses to the original value, matching the invariant already documented for quotes.

## Tests

* New `test_value_serialize_escapes_backslashes` cases pin the serialized spelling.
* New `test_marker_str_round_trip_preserves_backslashes` regression test fails before the fix and passes after.
* Full suite: 64209 passed, 1 skipped (glibc-only). `ruff check`, `ruff format --ch

## PR #1337: fix: validate sdist names and wheel build components
- State: `open` (unmerged; updated `2026-11-24T21:58:22Z`)
- URL: https://github.com/pypa/packaging/pull/1337

`parse_sdist_filename()` accepts names containing path separators or NUL, and a wheel build suffix can contain separators or an NTFS stream delimiter. This also admits those values after percent-decoding a Pylock URL.

Validate sdist names through `canonicalize_name(..., validate=True)` and restrict the build suffix at its parser boundary. Filename properties remain non-raising. Merged current main and retained its newline rejection (#1427). Tag validation is left to the existing #1413 rather than duplicated here; Unicode wheel project names remain with #1350.

Validation: 407 focused parser/tag/Pylock tests; configured full suite: 62,508 passed, 1 platform skip, 427 deselected. Pinned changed-file pre-commit checks passed (Ruff format/lint, mypy, typos, reStructuredText, and whitespace checks). AI-assisted maintenance.

