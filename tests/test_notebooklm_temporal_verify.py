from __future__ import annotations

import unittest
import hashlib
import tempfile

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import notebooklm_temporal_verify as verifier  # noqa: E402


def context_pack(status: str = "ok", complete: bool = True) -> dict:
    return {
        "status": status,
        "resolvedRange": {"startUtc": "2026-08-14T04:00:00.000Z", "endUtc": "2026-08-14T12:00:00.000Z"},
        "coverage": {"completeSelection": complete, "canonicalEventCount": 2, "includedEventCount": 2 if complete else 1},
        "selection": {"threadIds": ["thread-a"]},
        "messages": [
            {"eventId": "event-1", "threadId": "thread-a", "localDate": "2026-08-14", "text": "Refactored the temporal index and ran the test suite."},
            {"eventId": "event-2", "threadId": "thread-a", "localDate": "2026-08-14", "text": "Added a source-scoped verifier for NotebookLM citations."},
        ],
    }


def source_map(status: str = "ok") -> dict:
    return {"status": status, "mapping": [{"threadId": "thread-a", "sourceId": "source-a"}]}


def response(answer: str = "The index was refactored on 2026-08-14 [1].", **reference_overrides: object) -> dict:
    reference = {"source_id": "source-a", "citation_number": 1, "cited_text": "Refactored the temporal index and ran the test suite."}
    payload_overrides = {}
    for key, value in reference_overrides.items():
        if key in {"is_follow_up", "isFollowUp"}:
            payload_overrides[key] = value
        else:
            reference[key] = value
    return {"answer": answer, "is_follow_up": False, "references": [reference], **payload_overrides}


class NotebookLMTemporalVerifierTests(unittest.TestCase):
    def test_accepts_complete_in_scope_supported_citation(self) -> None:
        result = verifier.verify_remote_payload(response(), context_pack(), source_map())

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["decision"], "accept")
        self.assertEqual(result["codes"], [])
        self.assertEqual(result["citations"]["supportedReferenceCount"], 1)

    def test_rejects_out_of_scope_source(self) -> None:
        result = verifier.verify_remote_payload(response(source_id="source-outside"), context_pack(), source_map())

        self.assertEqual(result["decision"], "abstain")
        self.assertIn("SOURCE_SCOPE_INVALID", result["codes"])

    def test_rejects_citation_without_local_text_support(self) -> None:
        result = verifier.verify_remote_payload(response(cited_text="A claim that is not in the local event evidence."), context_pack(), source_map())

        self.assertEqual(result["status"], "abstained")
        self.assertIn("CITATION_EVIDENCE_UNMATCHED", result["codes"])

    def test_rejects_wrong_day_literal(self) -> None:
        result = verifier.verify_remote_payload(response("The work happened on 2026-08-13 [1]."), context_pack(), source_map())

        self.assertIn("TEMPORAL_LITERAL_OUT_OF_RANGE", result["codes"])
        self.assertEqual(result["decision"], "abstain")

    def test_degrades_when_local_selection_is_incomplete(self) -> None:
        result = verifier.verify_remote_payload(response(), context_pack(complete=False), source_map())

        self.assertEqual(result["status"], "degraded")
        self.assertIn("LOCAL_CONTEXT_INCOMPLETE", result["codes"])

    def test_rejects_follow_up_and_marker_mismatch(self) -> None:
        payload = response("A claim [2].", is_follow_up=True)
        result = verifier.verify_remote_payload(payload, context_pack(), source_map())

        self.assertIn("CONVERSATION_STATEFUL", result["codes"])
        self.assertIn("CITATION_MARKER_MISMATCH", result["codes"])

    def test_structural_citation_without_cited_text_is_not_promoted(self) -> None:
        result = verifier.verify_remote_payload(response(cited_text=None), context_pack(), source_map())

        self.assertIn("CITATION_EVIDENCE_UNMATCHED", result["codes"])
        self.assertEqual(result["decision"], "abstain")

    def test_current_local_projection_text_can_support_a_source_citation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            projection = Path(temporary) / "source.md"
            projection.write_text("Projected source wrapper with the verified source passage.", encoding="utf-8")
            digest = hashlib.sha256(projection.read_bytes()).hexdigest()
            scoped = source_map()
            scoped["mapping"][0]["sourceSha256"] = digest
            scoped["localSourceFiles"] = {"source-a": str(projection)}
            payload = response(cited_text="Projected source wrapper with the verified source passage.")

            result = verifier.verify_remote_payload(payload, context_pack(), scoped)

        self.assertEqual(result["decision"], "accept")
        self.assertEqual(result["sourceScope"]["localSourceFileDriftCount"], 0)

    def test_projection_digest_drift_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            projection = Path(temporary) / "source.md"
            projection.write_text("original source", encoding="utf-8")
            scoped = source_map()
            scoped["mapping"][0]["sourceSha256"] = hashlib.sha256(b"different source").hexdigest()
            scoped["localSourceFiles"] = {"source-a": str(projection)}

            result = verifier.verify_remote_payload(response(cited_text="original source with enough words to match."), context_pack(), scoped)

        self.assertIn("SOURCE_FILE_DRIFT", result["codes"])
        self.assertEqual(result["decision"], "abstain")


if __name__ == "__main__":
    unittest.main()
