from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import thread_temporal_release_monitor as monitor  # noqa: E402


def report(at: datetime, status: str = "ok", missing: bool = False) -> dict[str, object]:
    labels = ["projection", "sync", "retention"] if missing else ["projection", "temporal-refresh", "sync", "retention"]
    return {"CompletedAt": at.isoformat().replace("+00:00", "Z"), "Status": status, "Steps": [{"Label": label} for label in labels]}


class TemporalReleaseMonitorTests(unittest.TestCase):
    def test_short_clean_window_is_open(self) -> None:
        start = datetime(2026, 8, 1, tzinfo=UTC)
        result = monitor.evaluate([report(start), report(start + timedelta(hours=1))], now=start + timedelta(hours=2))
        self.assertEqual(result["status"], "open")
        self.assertEqual(result["failedRunCount"], 0)

    def test_start_boundary_excludes_pre_release_history(self) -> None:
        start = datetime(2026, 8, 1, tzinfo=UTC)
        old = report(start - timedelta(days=2), status="error", missing=True)
        current = report(start)
        result = monitor.evaluate([old, current], start_at=start)
        self.assertEqual(result["status"], "open")
        self.assertEqual(result["eligibleRunCount"], 1)
        self.assertEqual(result["failedRunCount"], 0)

    def test_full_clean_window_passes(self) -> None:
        start = datetime(2026, 8, 1, tzinfo=UTC)
        result = monitor.evaluate(
            [report(start + timedelta(hours=3 * index)) for index in range(57)],
            now=start + timedelta(hours=171),
            max_gap_hours=3,
        )
        self.assertEqual(result["status"], "pass")
        self.assertGreaterEqual(result["observedHours"], 168)

    def test_failure_or_missing_step_fails_even_after_long_window(self) -> None:
        start = datetime(2026, 8, 1, tzinfo=UTC)
        result = monitor.evaluate(
            [report(start), report(start + timedelta(hours=170), status="error", missing=True)],
            now=start + timedelta(hours=171),
        )
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["failedRunCount"], 1)
        self.assertEqual(result["missingStepRunCount"], 1)


if __name__ == "__main__":
    unittest.main()
