# Draft Release Announcement: `tomlkit` 0.15.3 (2026-11-24)

We are pleased to announce **`tomlkit` 0.15.3** — a compact 18-commit maintenance release containing 100% backward-compatible bug fixes with **zero behavior or exception-raising changes**.

## Highlights
- **Strict UTF-8 binary parsing (#721 / #720):** `tomlkit.parse()` / `loads()` now strictly decode `bytes` as UTF-8 and raise `UnicodeDecodeError` on invalid bytes, making 0.15.3 a safe drop-in replacement for stdlib `tomllib` on untrusted binary streams.
- **One-flag multiline array dumping (#706):** Callers can now pass `dumps(data, multiline=True)`.
- **Out-of-order table deletion fix (#635):** Deleting multiple keys from an out-of-order table proxy no longer raises `IndexError`.
- **Historical note:** Emptied dotted inline-table keys (#664) and literal-quote preservation (#325) already shipped in `0.15.2` and `0.15.1` respectively and are unchanged here.
