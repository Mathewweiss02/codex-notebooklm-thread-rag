from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "thread_rag_retention.py"
SPEC = importlib.util.spec_from_file_location("thread_rag_retention", MODULE_PATH)
retention = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(retention)


class RetentionTests(unittest.TestCase):
    def test_plan_and_apply_preserve_current_and_previous_lineage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "instance"
            projections = root / "projections" / "thread-a"
            runs = root / "runs"
            search = Path(temporary) / "search-runs"
            projections.mkdir(parents=True)
            runs.mkdir(parents=True)
            search.mkdir()
            parts = []
            for revision in (1, 2, 3):
                path = projections / f"r{revision:04d}-p001.md"
                path.write_text(f"revision {revision}\n", encoding="utf-8")
                parts.append(path)
            state = {
                "threads": {
                    "thread-a": {
                        "parts": [{"file": str(parts[2])}],
                        "previousSources": [{"file": str(parts[1])}],
                    }
                }
            }
            (root / "state.json").write_text(json.dumps(state), encoding="utf-8")
            old = datetime.now(UTC) - timedelta(days=60)
            for index in range(5):
                path = runs / f"runner-{index}.json"
                path.write_text('{"status":"ok"}', encoding="utf-8")
                os.utime(path, (old.timestamp() + index, old.timestamp() + index))
            for index in range(3):
                path = search / f"search-{index}.json"
                path.write_text('{"status":"ok"}', encoding="utf-8")
                os.utime(path, (old.timestamp() + index, old.timestamp() + index))

            plan = retention.build_plan(
                root,
                search_root=search,
                projection_revisions=2,
                retention_days=30,
                max_run_reports=2,
                max_search_reports=1,
            )
            targets = {(item["kind"], item["path"]) for item in plan["actions"]}
            self.assertIn(("projection", str(parts[0].relative_to(root))), targets)
            self.assertNotIn(("projection", str(parts[1].relative_to(root))), targets)
            self.assertNotIn(("projection", str(parts[2].relative_to(root))), targets)
            self.assertTrue(parts[0].is_file(), "planning must be non-destructive")

            retention.apply_plan(plan, root, search)
            self.assertFalse(parts[0].exists())
            self.assertTrue(parts[1].is_file())
            self.assertTrue(parts[2].is_file())
            self.assertLessEqual(len(list(runs.glob("*.json"))), 2)
            self.assertLessEqual(len(list(search.glob("*.json"))), 1)

    def test_state_cannot_protect_a_file_outside_projection_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "instance"
            (root / "projections" / "thread-a").mkdir(parents=True)
            outside = Path(temporary) / "outside.md"
            outside.write_text("keep me", encoding="utf-8")
            (root / "state.json").write_text(json.dumps({"threads": {"a": {"parts": [{"file": str(outside)}]}}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "escapes guarded root"):
                retention.build_plan(root)


if __name__ == "__main__":
    unittest.main()
