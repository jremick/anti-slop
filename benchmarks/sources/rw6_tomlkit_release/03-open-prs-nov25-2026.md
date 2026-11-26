# Open (Unmerged) Pull Requests on `python-poetry/tomlkit` as of 2026-11-25

Captured verbatim from `github.com/python-poetry/tomlkit` (`state: open`; NOT included in 0.15.3 release commit `d2aa305`).

## PR #721: fix: decode bytes strictly as UTF-8 when parsing (#720)
- State: `open` (unmerged; updated `2026-11-25T10:12:15Z`)
- URL: https://github.com/python-poetry/tomlkit/pull/721

### Summary

Fixes #720

When parsing bytes via `tomlkit.parse`, `tomlkit.loads`, or `tomlkit.load` on a binary stream, `Parser.__init__` previously called `tomlkit._compat.decode()`, which falls back across `["utf-8", "latin1", "ascii"]`. Because latin-1 accepts any byte sequence without error, invalid UTF-8 bytes were silently accepted and produced mojibake instead of raising an error.

The TOML specification mandates that TOML documents are encoded in UTF-8 (matching `tomllib` / `tomli` behavior).

### Changes
- In `tomlkit/parser.py`: decode `bytes` strictly as UTF-8 in `Parser.__init__` via `string.decode("utf-8")`.
- In `tests/test_api.py`: add unit tests verifying `parse()`, `loads()`, and `load()` raise `UnicodeDecodeError` on invalid UTF-8 bytes and parse valid UTF-8 bytes properly.
- In `tests/test_toml_tests.py`: add `test_invalid_encode_bytes` testing `invalid/encoding/*` cases with binary file reading (`"rb"`).

## PR #635: Keep out-of-order table indices valid after a table is removed
- State: `open` (unmerged; updated `2026-11-17T04:44:45Z`)
- URL: https://github.com/python-poetry/tomlkit/pull/635

## Summary

Deleting two keys through the same out-of-order table proxy raises or silently does nothing:

```python
src = '[tool.black]\nline-length = 88\n\n[project]\nname = "x"\n\n[tool.ruff]\nselect = ["E"]\n'
doc = tomlkit.parse(src); tool = doc["tool"]
del tool["black"]; del tool["ruff"]      # IndexError: list index out of range
tomlkit.parse(src)["tool"].clear()        # IndexError
```

With `[tool.a]`, `[tool.b]` and `[tool.c]` split by other tables, `clear()` returns but leaves `[tool.b]` and `[tool.c]` in the output. `_tables_map` holds positions in `self._tables`, and `_remove_table` removed the table with `list.remove` without shifting the later positions (`list.remove` also compares by equality, so it could take an equal empty table). It now removes the table by identity and shifts the later positions down by one.

`test_delete_keys_through_the_same_out_of_order_table` fails on master; dropping the shift or shifting the wrong side fails it too. `pytest tests` (1,069 passed) and `pre-commit run` on the changed files pass.

## Agent Drafting Metadata

- Agent: Claude Code
- Model: Claude
- Notes: Found by comparing edits against a tomllib model. I reviewed the change and

## PR #707: Fix serialization of dates and times created by factory methods
- State: `open` (unmerged; updated `2026-11-09T04:13:30Z`)
- URL: https://github.com/python-poetry/tomlkit/pull/707

## Summary

`Date.fromisoformat()`, `Date.fromordinal()` and the other inherited date factories return TOML items with an empty `_raw` value. `Time.fromisoformat()` does the same. Serializing one produces `value = \n`, which both Tomlkit and stdlib `tomllib` reject.

When no source text was supplied, generate the date's ISO text or use the existing local-time formatter. This follows the fallback already used by `DateTime`; parsed items retain their original text and comments.

Fifteen regressions cover date/time factories, fractional seconds, existing raw formatting and the unchanged DateTime behavior. On Python 3.11+, serialization is checked with the independent stdlib parser as well as Tomlkit. Before the fix: 11 failed, 4 passed. After the fix: all pass.

Validation on Windows / Python 3.13.4:
- Full suite including the pinned toml-test submodule: **1,449 passed**.
- All six configured pre-commit hooks: passed.
- New test file Mypy: passed. Full-tree Mypy reports the same 33 existing diagnostics on both base and patch.

## Duplicate Check

- [x] I searched the open PRs and found none that already fixes this issue.
- Related open PRs: #652 routes reflected addition through the w

## PR #706: Add a multiline array option to dump and dumps
- State: `open` (unmerged; updated `2026-11-07T23:03:32Z`)
- URL: https://github.com/python-poetry/tomlkit/pull/706

## Summary

Add `multiline=True` to `dumps()` and `dump()` so callers can render every array one item per line without traversing and changing the document first:

```python
tomlkit.dumps({"ports": [8001, 8002]}, multiline=True)
# ports = [
#     8001,
#     8002,
# ]
```

The option reaches arrays inside tables, inline tables, arrays of tables and other arrays. It uses the existing `Array.multiline(True)` formatting and preserves comments, document layout outside arrays and input objects. The default preserves existing formatting, including explicitly multiline arrays. Empty arrays stay empty.

Pass the option through internal render methods. Custom `as_string()` methods retain their no-argument interface and control their output. There is no shared formatting state. This implements the boolean option requested in #385; item-count and line-width selection are not added.

Fixes #385.

Validation on Linux / Python 3.12.12:

- 18 new tests fail against the original source because the option is unavailable; all pass with the change. Covers nested arrays, comments, aliases, custom renderers/encoders, reentrant calls, exceptions and concurrent renders.
- Full suite: 1,452 passing, inclu

