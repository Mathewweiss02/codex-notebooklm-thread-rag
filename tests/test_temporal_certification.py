from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import temporal_certification as certification  # noqa: E402


class TemporalCertificationTests(unittest.TestCase):
    def test_matrix_has_133_unique_rows(self) -> None:
        rows = certification.parse_matrix(
            Path(__file__).resolve().parents[1] / ".rnd" / "temporal-memory" / "certification-matrix.md"
        )
        self.assertEqual(len(rows), 133)
        self.assertEqual(len({row["id"] for row in rows}), 133)

    def test_pending_ledger_is_open_and_gate_rejects_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            matrix = root / "matrix.md"
            matrix.write_text(
                "| ID | Scenario | Required invariant | Test level |\n| --- | --- | --- | --- |\n| TIME-001 | Today | explicit | Unit |\n",
                encoding="utf-8",
            )
            ledger = root / "ledger.json"
            certification.init_ledger(matrix, ledger)
            rows, payload, errors = certification.validate_ledger(matrix, ledger)
            result = certification.summary(rows, payload, errors)
            self.assertEqual(result["status"], "open")
            self.assertEqual(result["releaseBlockingRowCount"], 1)

    def test_summary_flag_is_an_explicit_read_only_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            matrix = root / "matrix.md"
            matrix.write_text(
                "| ID | Scenario | Required invariant | Test level |\n| --- | --- | --- | --- |\n| TIME-001 | Today | explicit | Unit |\n",
                encoding="utf-8",
            )
            ledger = root / "ledger.json"
            certification.init_ledger(matrix, ledger)
            self.assertEqual(certification.main(["--matrix", str(matrix), "--ledger", str(ledger), "--summary"]), 0)

    def test_pass_requires_retained_execution_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            matrix = root / "matrix.md"
            matrix.write_text(
                "| ID | Scenario | Required invariant | Test level |\n| --- | --- | --- | --- |\n| TIME-001 | Today | explicit | Unit |\n",
                encoding="utf-8",
            )
            ledger = root / "ledger.json"
            certification.init_ledger(matrix, ledger)
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            payload["rows"]["TIME-001"]["status"] = "pass"
            ledger.write_text(json.dumps(payload), encoding="utf-8")
            _rows, _payload, errors = certification.validate_ledger(matrix, ledger)
            self.assertIn("row TIME-001 is pass without executedAt", errors)
            self.assertIn("row TIME-001 is pass without resultDigest", errors)

    def test_marking_a_row_records_evidence_without_promoting_the_whole_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            matrix = root / "matrix.md"
            matrix.write_text(
                "| ID | Scenario | Required invariant | Test level |\n| --- | --- | --- | --- |\n| TIME-001 | Today | explicit | Unit |\n| TIME-002 | Yesterday | explicit | Unit |\n",
                encoding="utf-8",
            )
            ledger = root / "ledger.json"
            certification.init_ledger(matrix, ledger)
            evidence = root / "fixture-run.json"
            evidence.write_text("{\"status\":\"pass\"}\n", encoding="utf-8")
            result = certification.mark_rows(
                matrix,
                ledger,
                ["TIME-001"],
                "pass",
                "fixture-run.json",
                certification.hashlib.sha256(evidence.read_bytes()).hexdigest(),
                "2026-08-14T00:00:00Z",
                "row-level retained run",
            )
            self.assertEqual(result["status"], "open")
            self.assertEqual(result["statusCounts"], {"pass": 1, "pending": 1})

    def test_mark_can_refresh_only_the_selected_row_after_its_evidence_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            matrix = root / "matrix.md"
            matrix.write_text(
                "| ID | Scenario | Required invariant | Test level |\n| --- | --- | --- | --- |\n| TIME-001 | Today | explicit | Unit |\n",
                encoding="utf-8",
            )
            ledger = root / "ledger.json"
            certification.init_ledger(matrix, ledger)
            evidence = root / "fixture-run.json"
            evidence.write_text("first\n", encoding="utf-8")
            first_digest = certification.hashlib.sha256(evidence.read_bytes()).hexdigest()
            certification.mark_rows(matrix, ledger, ["TIME-001"], "pass", "fixture-run.json", first_digest, None, "first")
            evidence.write_text("second\n", encoding="utf-8")
            second_digest = certification.hashlib.sha256(evidence.read_bytes()).hexdigest()
            result = certification.mark_rows(matrix, ledger, ["TIME-001"], "pass", "fixture-run.json", second_digest, None, "refreshed")
            self.assertEqual(result["status"], "pass")


if __name__ == "__main__":
    unittest.main()
