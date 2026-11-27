"""Data models for the SE3 spec-fidelity preference matcher and local runner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class WrittenPreference:
    importance: str
    statement: str


@dataclass(frozen=True)
class PreferenceClause:
    source_id: str
    field: str
    values: Tuple[str, ...]
    source_excerpt: str | None


@dataclass(frozen=True)
class RuleSource:
    source_id: str
    importance: str
    fields: Tuple[str, ...]
    clauses: Tuple[PreferenceClause, ...]


@dataclass(frozen=True)
class CompiledRules:
    sources: Tuple[RuleSource, ...]


@dataclass(frozen=True)
class PreparedRequest:
    prompt_bytes: int
    tool_count: int
    execution_mode: str
    truncated: bool
