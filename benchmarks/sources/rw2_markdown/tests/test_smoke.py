"""Baseline smoke tests for rw2_markdown (read-only)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

import markdown  # noqa: E402
from markdown.extensions.footnotes import FootnoteExtension  # noqa: E402
from markdown.extensions.toc import TocExtension  # noqa: E402


class MarkdownBaselineSmokeTests(unittest.TestCase):
    def test_basic_links_and_emphasis(self) -> None:
        html = markdown.markdown("See [docs](https://example.com) and *em* / **strong**.")
        self.assertEqual(
            html,
            '<p>See <a href="https://example.com">docs</a> and <em>em</em> / <strong>strong</strong>.</p>',
        )

    def test_rule_of_3_skipped_opener(self) -> None:
        self.assertEqual(
            markdown.markdown("***a**b*cd*e**f*g*h***"),
            "<p><em><strong>a</strong>b</em>cd<em>e**f</em>g<em>h</em>**</p>",
        )

    def test_footnotes_duplicate_references(self) -> None:
        ext = FootnoteExtension()
        md = markdown.Markdown(extensions=[ext])
        out = md.convert("One[^a] two[^a].\n\n[^a]: Note.")
        self.assertIn("fnref:a", out)
        self.assertIn("fnref2:a", out)
        self.assertEqual(ext.found_refs, {"fnref:a": 2})

    def test_toc_reuse_and_reset(self) -> None:
        md = markdown.Markdown(extensions=[TocExtension()])
        first = md.convert("# Heading\n\nBody")
        md.reset()
        second = md.convert("# Heading\n\nBody")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
