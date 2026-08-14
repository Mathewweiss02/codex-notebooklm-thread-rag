from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import thread_temporal_incremental_benchmark as benchmark  # noqa: E402


class TemporalIncrementalBenchmarkTests(unittest.TestCase):
    def test_no_change_and_one_thread_append_floors(self) -> None:
        result = benchmark.run_incremental(threads=3, events_per_thread=3, repeats=3)
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["noChange"]["floorPass"])
        self.assertTrue(result["oneThreadAppend"]["floorPass"])
        self.assertEqual(result["oneThreadAppend"]["finalEventCount"], 12)


if __name__ == "__main__":
    unittest.main()
