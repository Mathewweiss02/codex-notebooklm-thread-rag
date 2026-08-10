from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "notebooklm_thread_enroll.py"
SPEC = importlib.util.spec_from_file_location("notebooklm_thread_enroll", MODULE_PATH)
enroll = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(enroll)


class EnrollmentTests(unittest.TestCase):
    def test_scope_merge_is_stable_and_reports_only_new_tasks(self):
        merged, added = enroll.merge_scope(["a", "b"], ["b", "c", "a", "d"])
        self.assertEqual(merged, ["a", "b", "c", "d"])
        self.assertEqual(added, ["c", "d"])

    def test_capacity_requires_rolling_and_immediate_headroom(self):
        safe = enroll.capacity_decision(
            {"a": 2, "b": 1}, live_sources=3, pending_parts=1, source_limit=10, requested_reserve=3
        )
        self.assertTrue(safe["safe"])
        self.assertEqual(safe["steadyHeadroom"], 4)

        steady_unsafe = enroll.capacity_decision(
            {"a": 4, "b": 3}, live_sources=7, pending_parts=0, source_limit=10, requested_reserve=4
        )
        self.assertFalse(steady_unsafe["safe"])
        immediate_unsafe = enroll.capacity_decision(
            {"a": 3}, live_sources=9, pending_parts=2, source_limit=10, requested_reserve=3
        )
        self.assertFalse(immediate_unsafe["safe"])


if __name__ == "__main__":
    unittest.main()
