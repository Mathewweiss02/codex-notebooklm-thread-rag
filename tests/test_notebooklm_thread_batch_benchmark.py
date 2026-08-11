from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from notebooklm_thread_batch_benchmark import (  # noqa: E402
    answer_sections,
    build_packed_prompt,
    map_references_to_sections,
    unique_threads,
)


class BatchBenchmarkTests(unittest.TestCase):
    def test_sections_and_answer_offsets_map_references_per_question(self) -> None:
        answer = "Intro\n## Q1\nFirst answer [1].\n## Q2\nSecond answer [2].\n"
        refs = [
            SimpleNamespace(source_id="source-a", citation_number=1, answer_start_char=16),
            SimpleNamespace(source_id="source-b", citation_number=2, answer_start_char=41),
        ]
        mapped, unmapped = map_references_to_sections(answer, refs, 2)
        self.assertEqual(unmapped, 0)
        self.assertEqual([item.source_id for item in mapped[1]], ["source-a"])
        self.assertEqual([item.source_id for item in mapped[2]], ["source-b"])

    def test_missing_answer_offset_falls_back_to_citation_marker(self) -> None:
        answer = "## Q1\nFirst [1].\n## Q2\nSecond [2].\n"
        refs = [SimpleNamespace(source_id="source-b", citation_number=2, answer_start_char=None)]
        mapped, unmapped = map_references_to_sections(answer, refs, 2)
        self.assertEqual(unmapped, 0)
        self.assertEqual([item.source_id for item in mapped[2]], ["source-b"])

    def test_visible_marker_wins_over_drifted_answer_offset(self) -> None:
        answer = "## Q1\nFirst [1].\n## Q2\nSecond 【2】.\n"
        refs = [
            SimpleNamespace(source_id="source-a", citation_number=1, answer_start_char=0),
            SimpleNamespace(source_id="source-b", citation_number=2, answer_start_char=0),
        ]
        mapped, unmapped = map_references_to_sections(answer, refs, 2)
        self.assertEqual(unmapped, 0)
        self.assertEqual([item.source_id for item in mapped[1]], ["source-a"])
        self.assertEqual([item.source_id for item in mapped[2]], ["source-b"])

    def test_unmappable_reference_is_counted_without_answer_text(self) -> None:
        answer = "## Q1\nFirst answer without an inline marker.\n"
        refs = [SimpleNamespace(source_id="source-a", citation_number=7, answer_start_char=None)]
        mapped, unmapped = map_references_to_sections(answer, refs, 1)
        self.assertEqual(mapped[1], [])
        self.assertEqual(unmapped, 1)

    def test_unique_threads_deduplicates_split_sources_in_citation_order(self) -> None:
        refs = [
            SimpleNamespace(source_id="part-b", citation_number=3),
            SimpleNamespace(source_id="part-a", citation_number=1),
            SimpleNamespace(source_id="other", citation_number=2),
        ]
        mapping = {"part-a": "thread-a", "part-b": "thread-a", "other": "thread-b"}
        self.assertEqual(unique_threads(refs, mapping), ["thread-a", "thread-b"])

    def test_prompt_requires_independent_numbered_sections(self) -> None:
        prompt, redactions = build_packed_prompt([
            {"query": "Find alpha"},
            {"query": "Find beta"},
        ])
        self.assertEqual(redactions, 0)
        self.assertIn("Q1: Find alpha", prompt)
        self.assertIn("Q2: Find beta", prompt)
        self.assertIn("Do not combine questions", prompt)
        self.assertEqual(answer_sections("## Q1\nA\n## Q2\nB", 2), {1: (0, 8), 2: (8, 15)})


if __name__ == "__main__":
    unittest.main()
