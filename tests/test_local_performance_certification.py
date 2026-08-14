from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / ".rnd" / "temporal-memory" / "run-local-performance-certification.py"


def load_module():
    spec = importlib.util.spec_from_file_location("local_performance_certification", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load local performance certification harness")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LocalPerformanceCertificationTests(unittest.TestCase):
    def test_percentile_is_deterministic_and_uses_nearest_observed_rank(self) -> None:
        module = load_module()
        self.assertEqual(module.percentile([4, 1, 3, 2], 0.50), 2)
        self.assertEqual(module.percentile([4, 1, 3, 2], 0.95), 4)

    def test_aggregate_runs_retains_only_aggregate_coverage(self) -> None:
        module = load_module()
        result = module.aggregate_runs([
            {
                "status": "ok",
                "durationMs": 10,
                "coverage": {"includedEventCount": 3, "omittedEventCount": 0},
                "privateText": "must not be copied",
            },
            {
                "status": "ok",
                "durationMs": 20,
                "coverage": {"includedEventCount": 3, "omittedEventCount": 0},
                "privateText": "must not be copied",
            },
        ])
        self.assertEqual(result["runCount"], 2)
        self.assertEqual(result["p95Ms"], 20)
        self.assertEqual(result["coverage"]["includedEventCount"], 3)
        self.assertNotIn("privateText", json.dumps(result))

    def test_retained_performance_packet_is_aggregate_only_and_passes(self) -> None:
        packet = ROOT / ".rnd" / "temporal-memory" / "local-performance-certification-20260814-v3.json"
        self.assertTrue(packet.is_file())
        payload = json.loads(packet.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(set(payload["cases"]), {"PERF-001", "PERF-004", "PERF-005", "PERF-006"})
        self.assertEqual(payload["cases"]["PERF-006"]["measurement"]["coverage"]["omittedEventCount"], 0)
        serialized = json.dumps(payload)
        for forbidden in ('"threadId":', '"eventId":', '"prompt":', '"answer":', '"messageText":', "C:\\Users"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
