"""Frozen basic smoke tests for se4_greenfield_spec."""

from __future__ import annotations

import unittest

from se4_greenfield_spec import (
    PreferenceClause,
    WrittenPreference,
    compile_preference_rules,
    prepare_inference_batch,
)


class SmokeMatcherTests(unittest.TestCase):
    def test_basic_lifestyle_preference_compilation(self) -> None:
        items = {
            1: WrittenPreference("important", "Active runner who speaks Spanish"),
            2: WrittenPreference("very_important", "Non-smoker"),
        }
        clauses = [
            PreferenceClause("1", "fitness_level", ("Active",), "Active runner"),
            PreferenceClause("1", "languages", ("Spanish",), "speaks Spanish"),
            PreferenceClause("2", "smoking", ("No",), "Non-smoker"),
        ]
        compiled = compile_preference_rules(items, clauses)
        self.assertEqual(
            [(s.source_id, s.fields) for s in compiled.sources],
            [
                ("1", ("fitness_level", "languages")),
                ("2", ("smoking",)),
            ],
        )

    def test_stale_excerpt_drops_source(self) -> None:
        items = {3: WrittenPreference("important", "Enjoys hiking")}
        clauses = [PreferenceClause("3", "fitness_level", ("High",), "marathon runner")]
        compiled = compile_preference_rules(items, clauses)
        self.assertEqual(compiled.sources, ())


class SmokeRunnerTests(unittest.TestCase):
    def test_small_local_request_prepares_fast_tensor(self) -> None:
        batch = prepare_inference_batch("Summarize this draft", ["search", "calc"])
        self.assertEqual(batch.prompt_bytes, len("Summarize this draft".encode("utf-8")))
        self.assertEqual(batch.tool_count, 2)
        self.assertEqual(batch.execution_mode, "fast_tensor")
        self.assertFalse(batch.truncated)

    def test_empty_prompt_rejected(self) -> None:
        with self.assertRaises(ValueError):
            prepare_inference_batch("   ", [])


if __name__ == "__main__":
    unittest.main()
