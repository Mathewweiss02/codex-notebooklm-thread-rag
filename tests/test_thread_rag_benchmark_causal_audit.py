from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "thread_rag_benchmark_causal_audit.py"
SPEC = importlib.util.spec_from_file_location("thread_rag_benchmark_causal_audit", MODULE_PATH)
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(audit)


class CausalAuditTests(unittest.TestCase):
    def _write_packet(self, root: Path, *, include_check: bool = True, wrong_cause: bool = False) -> Path:
        score = {
            "split": "development",
            "caseDetailsSuppressed": False,
            "details": [
                {
                    "caseId": "miss-1",
                    "expectation": "match",
                    "candidateHit": True,
                    "top1Hit": False,
                    "abstained": False,
                    "passed": False,
                },
                {
                    "caseId": "negative-1",
                    "expectation": "no_match",
                    "candidateHit": None,
                    "top1Hit": None,
                    "abstained": True,
                    "passed": True,
                },
            ],
        }
        score_path = root / "score.json"
        score_path.write_text(json.dumps(score), encoding="utf-8")
        replay_path = root / "replay.json"
        replay_path.write_text('{"replayed":"raw citation order"}\n', encoding="utf-8")
        replay_digest = hashlib.sha256(replay_path.read_bytes()).hexdigest()
        score_digest = hashlib.sha256(score_path.read_bytes()).hexdigest()
        checks = []
        if include_check:
            checks.append({
                "checkId": "replay-1",
                "type": "replay",
                "prediction": "The same candidate set will put the expected thread below rank one.",
                "observed": "Replay reproduced the rank-one citation error.",
                "matches": True,
                "evidenceRefs": [{"path": "replay.json", "sha256": replay_digest}],
            })
        packet = {
            "contractVersion": audit.CONTRACT,
            "benchmark": {"scoreReport": "score.json", "scoreReportSha256": score_digest},
            "cases": [
                {
                    "caseId": "miss-1",
                    "outcome": "miss",
                    "causeClass": "semantic-candidate-omission" if wrong_cause else "raw-citation-order",
                    "claim": "The expected source was cited but not first.",
                    "prediction": "A replay of the same candidate set will reproduce the citation-order miss.",
                    "independentCheckIds": ["replay-1"] if include_check else [],
                },
                {
                    "caseId": "negative-1",
                    "outcome": "no-match",
                    "causeClass": "true-no-match",
                    "claim": "The negative query correctly abstained.",
                    "prediction": "A clean replay will remain abstained.",
                    "independentCheckIds": [],
                },
            ],
            "independentChecks": checks,
            "claimedImprovements": [],
        }
        packet_path = root / "packet.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        return packet_path

    def test_valid_packet_requires_and_accepts_independent_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = audit.audit_packet(self._write_packet(Path(temporary)))
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["failureCaseCount"], 1)
            self.assertEqual(result["independentCheckCount"], 1)

    def test_failure_without_independent_check_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = audit.audit_packet(self._write_packet(Path(temporary), include_check=False))
            self.assertEqual(result["status"], "invalid")
            self.assertTrue(any("independent check" in error for error in result["errors"]))

    def test_cause_that_contradicts_observed_rank_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = audit.audit_packet(self._write_packet(Path(temporary), wrong_cause=True))
            self.assertEqual(result["status"], "invalid")
            self.assertTrue(any("cause class contradicts" in error for error in result["errors"]))

    def test_claimed_improvement_binds_distinct_before_and_after_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            packet_path = self._write_packet(root)
            before = root / "before.json"
            after = root / "after.json"
            before.write_text('{"top1":0.5}\n', encoding="utf-8")
            after.write_text('{"top1":1.0}\n', encoding="utf-8")
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            packet["claimedImprovements"] = [{
                "caseId": "miss-1",
                "prediction": "The ranking change will move the expected thread to rank one.",
                "observedChange": "The independent replay moved the expected thread to rank one.",
                "beforeReport": {"path": "before.json", "sha256": hashlib.sha256(before.read_bytes()).hexdigest()},
                "afterReport": {"path": "after.json", "sha256": hashlib.sha256(after.read_bytes()).hexdigest()},
                "independentCheckIds": ["replay-1"],
            }]
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            result = audit.audit_packet(packet_path)
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["claimedImprovementCount"], 1)

    def test_holdout_details_cannot_be_disclosed_in_public_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet_path = self._write_packet(Path(temporary))
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            score_path = Path(temporary) / "score.json"
            score = json.loads(score_path.read_text(encoding="utf-8"))
            score["split"] = "holdout"
            score["caseDetailsSuppressed"] = True
            score_path.write_text(json.dumps(score), encoding="utf-8")
            packet["benchmark"]["scoreReportSha256"] = hashlib.sha256(score_path.read_bytes()).hexdigest()
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            with self.assertRaisesRegex(audit.CausalAuditError, "sealed holdout"):
                audit.audit_packet(packet_path)


if __name__ == "__main__":
    unittest.main()
