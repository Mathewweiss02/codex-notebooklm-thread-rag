from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import thread_temporal_scale_benchmark as benchmark  # noqa: E402


class TemporalScaleBenchmarkTests(unittest.TestCase):
    def test_small_scale_run_matches_independent_oracle(self) -> None:
        result = benchmark.run_scale(multipliers=[1, 2], base_threads=2, events_per_thread=3, repeats=2)
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["correctness"])
        self.assertEqual([row["oracleEventCount"] for row in result["rows"]], [6, 12])
        self.assertTrue(all(row["correctness"] for row in result["rows"]))


if __name__ == "__main__":
    unittest.main()
