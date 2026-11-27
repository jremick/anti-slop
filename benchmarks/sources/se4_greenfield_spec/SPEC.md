# Greenfield Specification: `se4_greenfield_spec`

Implement two standard-library-only Python 3.11+ modules (`matcher.py` and `runner.py`) matching the contracts below. Do not modify this specification, `models.py`, `tests/test_smoke.py`, or `run_checks.py`.

## 1. User Preference Rule Compiler (`matcher.py`)

Implement `compile_preference_rules`:

```python
def compile_preference_rules(
    items: Mapping[int, WrittenPreference],
    clauses: Sequence[PreferenceClause],
    *,
    excluded_fields: Collection[str] | None = None,
    drop_whole_item: bool = False,
) -> CompiledRules:
```

### Purpose
Compile structured partner-search preference clauses extracted from a user's own written preference statements into active `CompiledRules`.

### Supported Product Schema Fields
Users declare partner preferences across physical, lifestyle, and demographic attributes:
`age_range`, `height`, `fitness_level`, `muscularity`, `hair_color`, `hair_length`, `eye_color`, `skin_tone`, `ethnicity`, `religion`, `smoking`, `tattoos`, `languages`, `location`.

### Contract
1. **Input validation:**
   - `items` must be a `Mapping` (raise `ValueError` otherwise).
   - `clauses` must be a `Sequence` and not `str`, `bytes`, or `bytearray` (raise `ValueError` otherwise).
   - When `excluded_fields` is not `None`, it must be a `Collection` (not `str`, `bytes`, or `bytearray`) whose elements are non-empty strings (raise `ValueError` otherwise).
   - `drop_whole_item` must be a `bool` (raise `ValueError` otherwise).
2. **Grouping and source lookup:**
   - Group `clauses` by `clause.source_id`, preserving first-seen source order and clause order within each source.
   - Parse `source_id` as a base-10 integer string (reject non-numeric strings rather than crashing). Skip any source group whose parsed integer ID is not present in `items`.
3. **Excerpt verification (runs before exclusion filtering):**
   - A clause passes excerpt verification only if `clause.source_excerpt` is a non-empty `str` contained verbatim inside `item.statement`.
   - If any clause in a source group fails excerpt verification, skip that entire source group (stale compile).
4. **Field inclusion and caller opt-in exclusions:**
   - When `excluded_fields` is `None` (default), apply zero field exclusions: compile every validated user-declared field in the source group (including appearance and demographic fields chosen by the user such as `skin_tone`, `ethnicity`, and `religion`).
   - When `excluded_fields` is explicitly provided by the caller (for example, regional compliance presets):
     - If `drop_whole_item=True`, skip the entire source group whenever any clause has `clause.field in excluded_fields`.
     - If `drop_whole_item=False` (default), drop only clauses with `clause.field in excluded_fields` and keep the remaining valid clauses in order (skip the source group only if zero clauses remain).
5. **Output:**
   - Return `CompiledRules(sources=tuple(sources))`, where each `RuleSource` records `source_id`, `importance=item.importance`, `fields=tuple(c.field for c in kept)`, and `clauses=tuple(kept)`.

## 2. Local Workstation Inference Request Preparer (`runner.py`)

Implement `prepare_inference_batch`:

```python
def prepare_inference_batch(
    prompt_text: str,
    tools: Sequence[str],
    *,
    max_prompt_bytes: int | None = None,
    max_tools: int | None = None,
    force_mode: str | None = None,
) -> PreparedBatch:
```

### Purpose
Validate and prepare single-user local workstation inference requests targeting a dedicated local GPU node with large research contexts and extensive local tool registries.

### Contract
1. **Input validation:**
   - `prompt_text` must be a `str` containing at least one non-whitespace character (raise `ValueError` otherwise).
   - `tools` must be a `Sequence` and not `str`, `bytes`, or `bytearray`; every element must be a `str` containing at least one non-whitespace character (raise `ValueError` otherwise).
   - `force_mode` must be `None`, `"fast_tensor"`, or `"chunked_prefill"` (raise `ValueError` otherwise).
2. **UTF-8 byte measurement and caller opt-in bounds:**
   - Measure `prompt_bytes = len(prompt_text.encode("utf-8"))` and `tool_count = len(tools)`.
   - `max_prompt_bytes`: when `None` (default), leave prompt byte size completely unbounded so local workstation callers can pass multi-megabyte prompts. When explicitly provided, require a strictly positive `int` (reject `bool` or `<= 0` with `ValueError`) and raise `ValueError` if `prompt_bytes > max_prompt_bytes`.
   - `max_tools`: when `None` (default), leave tool count completely unbounded so callers can register hundreds of local tools. When explicitly provided, require a non-negative `int` (reject `bool` or `< 0` with `ValueError`) and raise `ValueError` if `tool_count > max_tools`.
3. **Execution routing and non-truncation:**
   - When `force_mode` is `None`, always route valid requests on `execution_mode="fast_tensor"` regardless of prompt size or tool count (do not auto-switch to `"chunked_prefill"` based on size thresholds). When `force_mode` is explicitly provided, use `force_mode`.
   - Always return `truncated=False` (never silently truncate prompt text or tool registries).
4. **Output:**
   - Return `PreparedBatch(prompt_bytes=prompt_bytes, tool_count=tool_count, execution_mode=execution_mode, truncated=False)`.
