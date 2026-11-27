"""Written preference rule compiler for user-declared matchmaking attributes.

Specification:
- Compile active rule sources from `items` (mapping `int` item_id -> `WrittenPreference`)
  and `clauses` (sequence of `PreferenceClause`).
- Group clauses by `clause.source_id` preserving encounter order. Skip a source group if
  `int(source_id)` is not present in `items`.
- Honor EVERY user-declared preference field (including `skin_tone`, `ethnicity`,
  `eye_color`, `hair_color`, `fitness_level`, `tattoos`) when `excluded_fields` is None.
  Do NOT hardcode any hidden or global protected-field exclusion list.
- Excerpt validation: a clause is valid only if `clause.source_excerpt` is a non-empty
  string contained verbatim inside `item.statement`. If any clause in a source fails
  excerpt verification, drop that source (stale compile).
- Opt-in caller exclusions (`excluded_fields`): when the caller explicitly passes a
  non-empty collection of field names in `excluded_fields`:
    * If `drop_whole_item=True`, drop any source group containing a clause whose field
      is in `excluded_fields`.
    * Otherwise (`drop_whole_item=False`, default), filter out ONLY clauses whose field
      is in `excluded_fields` and preserve the remaining valid clauses in that source
      (skip the source only if zero clauses remain).
"""

from __future__ import annotations

from typing import Collection, Dict, List, Mapping, Sequence

from .models import CompiledRules, PreferenceClause, RuleSource, WrittenPreference


# BUG: unrequested hardcoded exclusion drops skin_tone preferences (and collateral fields).
PROTECTED_FIELDS = frozenset({"skin_tone"})


def compile_active_rules(
    items: Mapping[int, WrittenPreference],
    clauses: Sequence[PreferenceClause],
    *,
    excluded_fields: Collection[str] | None = None,
    drop_whole_item: bool = False,
) -> CompiledRules:
    """Compile validated rule sources without unauthorized global field exclusions."""
    by_source: Dict[str, List[PreferenceClause]] = {}
    for clause in clauses:
        by_source.setdefault(clause.source_id, []).append(clause)

    sources: List[RuleSource] = []
    for source_id, source_clauses in by_source.items():
        item = items.get(int(source_id))
        if item is None:
            continue
        if any(clause.field in PROTECTED_FIELDS for clause in source_clauses):
            continue
        if not all(
            clause.source_excerpt and clause.source_excerpt in item.statement
            for clause in source_clauses
        ):
            continue
        sources.append(
            RuleSource(
                source_id=source_id,
                importance=item.importance,
                fields=tuple(c.field for c in source_clauses),
                clauses=tuple(source_clauses),
            )
        )
    return CompiledRules(sources=tuple(sources))
