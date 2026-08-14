from __future__ import annotations

import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import notebooklm_temporal_synthesis_compare as synthesis  # noqa: E402


class NotebookLMTemporalSynthesisCompareTests(unittest.TestCase):
    def test_scope_parser_accepts_supported_reference_shapes(self) -> None:
        payload = {
            "answer": "Answer [1]",
            "references": [
                {"source_id": "source-a"},
                {"sourceId": "source-b"},
                {"id": "source-a"},
            ],
        }

        result = synthesis.parse_remote_payload(payload, {"source-a", "source-b"})

        self.assertEqual(result["answerChars"], len("Answer [1]"))
        self.assertEqual(result["referenceCount"], 3)
        self.assertEqual(result["referencedSourceCount"], 2)
        self.assertEqual(result["referencedSourceIdsInScope"], 2)
        self.assertEqual(result["referencedSourceIdsOutOfScope"], 0)
        self.assertTrue(result["citationScopeValid"])
        self.assertTrue(result["answerContainsCitationMarker"])

    def test_out_of_scope_reference_is_invalid_even_with_other_valid_references(self) -> None:
        payload = {
            "text": "Answer 【1】",
            "sources": [{"source_id": "source-a"}, {"source_id": "source-outside"}],
        }

        result = synthesis.parse_remote_payload(payload, {"source-a"})

        self.assertEqual(result["referencedSourceIdsInScope"], 1)
        self.assertEqual(result["referencedSourceIdsOutOfScope"], 1)
        self.assertFalse(result["citationScopeValid"])

    def test_malformed_reference_entries_do_not_create_false_scope_matches(self) -> None:
        payload = {"answer": "No source citation", "references": ["source-a", {}, None]}

        result = synthesis.parse_remote_payload(payload, {"source-a"})

        self.assertEqual(result["referenceCount"], 3)
        self.assertEqual(result["referencedSourceCount"], 0)
        self.assertTrue(result["citationScopeValid"])
        self.assertFalse(result["answerContainsCitationMarker"])

    def test_non_object_payload_fails_closed(self) -> None:
        with self.assertRaises(synthesis.SynthesisExperimentError) as caught:
            synthesis.parse_remote_payload([], set())

        self.assertEqual(caught.exception.code, "REMOTE_INVALID")


if __name__ == "__main__":
    unittest.main()
