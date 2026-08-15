from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import thread_rag_benchmark_causal_audit as audit  # noqa: E402
import thread_rag_benchmark_promote as promote  # noqa: E402


class BenchmarkPromotionTests(unittest.TestCase):
    def _valid_packet(self, root: Path, *, include_check: bool = True) -> tuple[Path, Path]:
        score = {
            "split": "development",
            "caseDetailsSuppressed": False,
            "passed": True,
            "gates": {
                "candidateRecall100": True,
                "hybridTop1": True,
                "falsePositiveRate": True,
                "falseNegativeRate": True,
            },
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
        checks = []
        if include_check:
            checks.append({
                "checkId": "replay-1",
                "type": "replay",
                "prediction": "The expected thread will remain below rank one.",
                "observed": "The replay reproduced the rank-one citation error.",
                "matches": True,
                "evidenceRefs": [{"path": "replay.json", "sha256": replay_digest}],
            })
        packet = {
            "contractVersion": audit.CONTRACT,
            "benchmark": {
                "scoreReport": "score.json",
                "scoreReportSha256": hashlib.sha256(score_path.read_bytes()).hexdigest(),
            },
            "cases": [
                {
                    "caseId": "miss-1",
                    "outcome": "miss",
                    "causeClass": "raw-citation-order",
                    "claim": "The expected source was cited but not first.",
                    "prediction": "A replay will reproduce the citation-order miss.",
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
        packet_path = root / "causal.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        return score_path, packet_path

    def test_promotion_certificate_requires_passing_causal_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            score_path, packet_path = self._valid_packet(root)
            output = root / "promotion.json"
            certificate = promote.promote_packet(score_path, packet_path, output)
            self.assertEqual(certificate["status"], "pass")
            self.assertEqual(certificate["causalAudit"]["status"], "pass")
            self.assertTrue(output.is_file())

    def test_promotion_refuses_a_score_without_independent_explanation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            score_path, packet_path = self._valid_packet(root, include_check=False)
            with self.assertRaisesRegex(audit.CausalAuditError, "causal evidence"):
                promote.promote_packet(score_path, packet_path, root / "promotion.json")

    def test_promotion_refuses_an_incomplete_quantitative_gate_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            score_path, packet_path = self._valid_packet(root)
            score = json.loads(score_path.read_text(encoding="utf-8"))
            score["gates"].pop("falseNegativeRate")
            score_path.write_text(json.dumps(score), encoding="utf-8")
            with self.assertRaisesRegex(audit.CausalAuditError, "missing a required"):
                promote.promote_packet(score_path, packet_path, root / "promotion.json")


if __name__ == "__main__":
    unittest.main()
