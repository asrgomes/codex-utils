from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_merge_conflict_review.py"
SPEC = importlib.util.spec_from_file_location("generate_merge_conflict_review", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class ConflictReportGeneratorTest(unittest.TestCase):
    def test_parse_diff3_conflict(self) -> None:
        parsed = module.parse_conflict_file(
            "Example.java",
            [
                "class Example {",
                "<<<<<<< HEAD",
                "    int value = 1;",
                "||||||| base",
                "    int value = 0;",
                "=======",
                "    int value = 2;",
                ">>>>>>> feature",
                "}",
            ],
        )

        self.assertEqual(len(parsed.hunks), 1)
        hunk = parsed.hunks[0]
        self.assertEqual(hunk.left_label, "HEAD")
        self.assertEqual(hunk.right_label, "feature")
        self.assertEqual(hunk.left_lines, ["    int value = 1;"])
        self.assertEqual(hunk.base_lines, ["    int value = 0;"])
        self.assertEqual(hunk.right_lines, ["    int value = 2;"])

    def test_auto_proposal_uses_non_empty_side(self) -> None:
        hunk = module.ConflictHunk(
            path="Example.java",
            file_index=1,
            global_index=1,
            marker_start_line=1,
            marker_end_line=4,
            left_label="HEAD",
            right_label="feature",
            left_lines=[],
            right_lines=["import java.util.List;"],
            base_lines=[],
        )

        proposed, reason = module.choose_proposal(hunk, "auto", {})

        self.assertEqual(proposed, ["import java.util.List;"])
        self.assertIn("incoming content", reason)

    def test_default_diff_context_matches_main_context(self) -> None:
        args = module.parse_args([])

        self.assertEqual(args.context, 15)
        self.assertEqual(args.diff_context, 15)

    def test_inline_diff_highlights_changed_token(self) -> None:
        left, right = module.token_diff_html("return valueOne;", "return valueTwo;")

        self.assertIn("inline-left", left)
        self.assertIn("inline-right", right)
        self.assertIn("value", left)
        self.assertIn("value", right)

    def test_side_by_side_diff_has_equal_panel_markup(self) -> None:
        rendered = module.render_side_by_side_diff(
            ["return valueOne;"],
            ["return valueTwo;"],
            (0, 1),
            (0, 1),
            0,
            "Closest common ancestor",
            "Left/current branch",
        )

        self.assertIn("side-by-side-diff", rendered)
        self.assertIn("diff-side diff-side-base", rendered)
        self.assertIn("diff-side diff-side-target", rendered)
        self.assertIn("Closest common ancestor", rendered)
        self.assertIn("Left/current branch", rendered)
        self.assertIn("inline-change", rendered)
        self.assertIn("@@ -1,1 +1,1 @@", rendered)
        self.assertIn("<td class=\"ln\">1</td>", rendered)
        self.assertEqual(rendered.count("<tr class=\"diff-change\">"), 2)

    def test_side_by_side_diff_uses_semantic_add_remove_colors(self) -> None:
        added = module.render_side_by_side_diff(
            [],
            ["added"],
            (0, 0),
            (0, 1),
            0,
            "Closest common ancestor",
            "Left/current branch",
        )
        removed = module.render_side_by_side_diff(
            ["removed"],
            [],
            (0, 1),
            (0, 0),
            0,
            "Closest common ancestor",
            "Left/current branch",
        )
        css = module.render_css()

        self.assertIn("diff-add", added)
        self.assertIn("inline-add", added)
        self.assertIn("diff-remove", removed)
        self.assertIn("inline-remove", removed)
        self.assertIn("tr.diff-remove td { background: rgba(255, 123, 114", css)
        self.assertIn("tr.diff-add td { background: rgba(63, 185, 80", css)
        self.assertIn("tr.diff-change td { background: rgba(250, 204, 21", css)
        self.assertNotIn(".ancestor-diff:first-child tr.diff-add", css)

    def test_report_css_stretches_side_by_side_panels(self) -> None:
        css = module.render_css()

        self.assertIn(".panels, .side-by-side-diff", css)
        self.assertIn("align-items: stretch", css)
        self.assertIn(".side, .diff-side", css)
        self.assertIn("flex-direction: column", css)


if __name__ == "__main__":
    unittest.main()
