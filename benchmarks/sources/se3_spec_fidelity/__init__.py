"""Spec-fidelity benchmark fixture package (SE3): preference matcher and local request runner."""

from .matcher import compile_active_rules
from .models import CompiledRules, PreferenceClause, PreparedRequest, RuleSource, WrittenPreference
from .runner import prepare_request

__all__ = [
    "CompiledRules",
    "PreferenceClause",
    "PreparedRequest",
    "RuleSource",
    "WrittenPreference",
    "compile_active_rules",
    "prepare_request",
]
