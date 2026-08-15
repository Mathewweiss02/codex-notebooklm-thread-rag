from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from notebooklm_temporal_pack_benchmark import (  # noqa: E402
    answer_sections,
    build_packed_prompt,
    map_references_to_sections,
    score_structural_response,
)


class TemporalPromptPackTests(unittest.TestCase):
    def test_prompt_is_atomic_and_redaction_aware(self) -> None:
        prompt, redactions = build_packed_prompt(
            [{"query": "Find the notebooklm work"}, {"query": "Find the token sk-test-1234567890"}],
            "today",
            "America/New_York",
        )
        self.assertEqual(redactions, 1)
        self.assertIn("Q1: Find the notebooklm work", prompt)
        self.assertIn("Q2:", prompt)
        self.assertIn("Do not guess", prompt)

    def test_marker_first_mapping_survives_drifted_offsets(self) -> None:
        answer = "## Q1\nAlpha [1].\n## Q2\nBeta [2].\n"
        refs = [
            {"source_id": "source-a", "citation_number": 1, "answer_start_char": 0},
            {"source_id": "source-b", "citation_number": 2, "answer_start_char": 0},
        ]
        mapped, unmapped = map_references_to_sections(answer, refs, 2)
        self.assertEqual(unmapped, 0)
        self.assertEqual([item["source_id"] for item in mapped[1]], ["source-a"])
        self.assertEqual([item["source_id"] for item in mapped[2]], ["source-b"])

    def test_unicode_citation_marker_maps_to_the_containing_section(self) -> None:
        answer = "## Q1\nAlpha 【1】.\n## Q2\nBeta 【2】.\n"
        refs = [
            {"source_id": "source-a", "citation_number": 1},
            {"source_id": "source-b", "citation_number": 2},
        ]
        mapped, unmapped = map_references_to_sections(answer, refs, 2)
        self.assertEqual(unmapped, 0)
        self.assertEqual([item["source_id"] for item in mapped[1]], ["source-a"])
        self.assertEqual([item["source_id"] for item in mapped[2]], ["source-b"])

    def test_missing_heading_and_out_of_scope_reference_degrade(self) -> None:
        answer = "## Q1\nAlpha [1].\n"
        refs = [{"source_id": "source-outside", "citation_number": 1}]
        result = score_structural_response(answer, refs, 2, {"source-a"})
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["missingHeadingCount"], 1)
        self.assertEqual(result["unmappedReferenceCount"], 0)
        self.assertEqual(result["outOfScopeReferenceCount"], 1)

    def test_structural_response_passes_only_when_every_section_and_reference_maps(self) -> None:
        answer = "## Q1\nAlpha [1].\n## Q2\nBeta [2].\n"
        refs = [
            {"source_id": "source-a", "citation_number": 1},
            {"source_id": "source-b", "citation_number": 2},
        ]
        result = score_structural_response(answer, refs, 2, {"source-a", "source-b"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mappedReferenceCount"], 2)

    def test_duplicate_and_out_of_range_headings_degrade(self) -> None:
        answer = "## Q1\nAlpha [1].\n## Q1\nDuplicate.\n## Q2\nBeta [2].\n## Q9\nExtra.\n"
        refs = [
            {"source_id": "source-a", "citation_number": 1},
            {"source_id": "source-b", "citation_number": 2},
        ]
        result = score_structural_response(answer, refs, 2, {"source-a", "source-b"})
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["duplicateHeadingCount"], 1)
        self.assertEqual(result["outOfRangeHeadingCount"], 1)

    def test_heading_parser_rejects_duplicate_or_out_of_range_questions(self) -> None:
        self.assertEqual(answer_sections("## Q1\nA\n## Q1\nB\n## Q3\nC", 2), {1: (0, 23)})


if __name__ == "__main__":
    unittest.main()
