"""User preference rule compiler. See SPEC.md for full requirements."""

from __future__ import annotations

from typing import Collection, Mapping, Sequence

from .models import CompiledRules, PreferenceClause, WrittenPreference


def compile_preference_rules(
    items: Mapping[int, WrittenPreference],
    clauses: Sequence[PreferenceClause],
    *,
    excluded_fields: Collection[str] | None = None,
    drop_whole_item: bool = False,
) -> CompiledRules:
    """Compile validated preference rule sources per SPEC.md."""
    raise NotImplementedError("Implement compile_preference_rules per SPEC.md")
