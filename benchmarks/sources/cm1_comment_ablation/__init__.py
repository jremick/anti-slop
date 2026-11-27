"""Controlled comment-hygiene ablation fixtures (CM1).

Contains three sibling variants with 100% identical executable Python ASTs
differing strictly in comments:
  - no_comments: zero `#` comments
  - invariant_comments: three crisp 1-line `# INVARIANT:` why-comments
  - comment_traps: defective commented-out code blocks, a stale contradictory
    comment, and narrating boilerplate comments
"""

from __future__ import annotations

VARIANTS: tuple[str, ...] = ("no_comments", "invariant_comments", "comment_traps")
