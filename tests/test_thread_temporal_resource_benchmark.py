from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import thread_temporal_resource_benchmark as benchmark  # noqa: E402


class TemporalResourceBenchmarkTests(unittest.TestCase):
    def test_repeated_queries_match_and_stay_bounded(self) -> None:
        result = benchmark.run(iterations=8, thread_count=4, events_per_thread=4)
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["queryCorrect"])
        self.assertTrue(result["boundedMemory"])
        self.assertTrue(result["boundedHandles"])


if __name__ == "__main__":
    unittest.main()
