from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import thread_temporal_soak as soak  # noqa: E402


class TemporalSoakHarnessTests(unittest.TestCase):
    def test_extended_cycle_clock_remains_valid_past_one_hour(self) -> None:
        result = soak.run(60)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["successfulCycles"], 60)
        self.assertTrue(result["recoveryPass"])
        self.assertTrue(result["failClosedPass"])


if __name__ == "__main__":
    unittest.main()
