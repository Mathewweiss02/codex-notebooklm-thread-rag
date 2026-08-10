from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "notebooklm_thread_sync.py"
SPEC = importlib.util.spec_from_file_location("notebooklm_thread_sync", MODULE_PATH)
sync = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sync)


@dataclass
class FakeSource:
    id: str
    title: str


class FakeSources:
    def __init__(self, sources=None, fail_add_number=None):
        self.items = list(sources or [])
        self.fail_add_number = fail_add_number
        self.add_calls = 0
        self.deleted = []

    async def list(self, notebook_id, strict=True):
        return list(self.items)

    async def add_file(self, notebook_id, path, **kwargs):
        self.add_calls += 1
        if self.fail_add_number == self.add_calls:
            raise RuntimeError("simulated interrupted upload")
        source = FakeSource(f"new-{len(self.items) + 1}", kwargs["title"])
        self.items.append(source)
        return source

    async def delete(self, notebook_id, source_id):
        self.deleted.append(source_id)
        self.items = [item for item in self.items if item.id != source_id]


class FakeClient:
    def __init__(self, sources):
        self.sources = sources


def args(**overrides):
    values = {"dry_run": False, "validate_only": False, "swap_old": True, "wait_timeout": 5.0}
    values.update(overrides)
    return SimpleNamespace(**values)


def part(path: Path, title: str, source_id=None):
    path.write_text(f"# {title}\n", encoding="utf-8")
    return {"part": 1, "totalParts": 1, "file": str(path), "title": title, "bytes": path.stat().st_size, "sourceId": source_id, "status": "projected"}


class SyncTests(unittest.IsolatedAsyncioTestCase):
    def test_source_capacity_boundaries(self):
        sync.ensure_source_capacity(299, 1, 300)
        with self.assertRaisesRegex(ValueError, "Source cap would be exceeded"):
            sync.ensure_source_capacity(299, 2, 300)

    def test_ready_old_retained_is_a_stable_current_mode(self):
        live = FakeSource("current", "current title")
        thread = {
            "threadId": "retained-thread",
            "revision": 2,
            "uploadRevision": 2,
            "uploadStatus": "ready-old-retained",
            "previousSources": [{"sourceId": "old", "title": "old title"}],
            "parts": [{"sourceId": "current", "title": "current title"}],
        }
        self.assertTrue(sync.thread_is_current(thread, {"current": live}))

    async def test_guarded_swap_deletes_only_matching_prior_lineage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current_part = part(root / "new.md", "new revision")
            thread = {
                "threadId": "thread-1",
                "revision": 2,
                "parts": [current_part],
                "previousSources": [{"sourceId": "old-1", "title": "old revision"}],
            }
            state = {"threads": {"thread-1": thread}}
            state_path = root / "state.json"
            old = FakeSource("old-1", "old revision")
            sources = FakeSources([old])
            result = await sync.sync_thread(FakeClient(sources), "notebook", thread, state, state_path, {old.id: old}, {old.title: [old]}, args())
            self.assertEqual(result["deletedOld"], 1)
            self.assertEqual(sources.deleted, ["old-1"])
            self.assertEqual(thread["previousSources"], [])
            self.assertEqual(thread["uploadStatus"], "ready")

    async def test_lineage_mismatch_refuses_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current_part = part(root / "new.md", "new revision")
            thread = {
                "threadId": "thread-2",
                "revision": 2,
                "parts": [current_part],
                "previousSources": [{"sourceId": "old-2", "title": "expected old title"}],
            }
            state = {"threads": {"thread-2": thread}}
            state_path = root / "state.json"
            old = FakeSource("old-2", "different live title")
            sources = FakeSources([old])
            with self.assertRaisesRegex(ValueError, "lineage-mismatched deletion"):
                await sync.sync_thread(FakeClient(sources), "notebook", thread, state, state_path, {old.id: old}, {old.title: [old]}, args())
            self.assertEqual(sources.deleted, [])

    async def test_interrupted_upload_checkpoints_and_resumes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = part(root / "one.md", "part one")
            second = part(root / "two.md", "part two")
            second["part"] = 2
            first["totalParts"] = second["totalParts"] = 2
            thread = {"threadId": "thread-3", "revision": 1, "parts": [first, second], "previousSources": []}
            state = {"threads": {"thread-3": thread}}
            state_path = root / "state.json"
            failing = FakeSources(fail_add_number=2)
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                await sync.sync_thread(FakeClient(failing), "notebook", thread, state, state_path, {}, {}, args())
            checkpoint = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["threads"]["thread-3"]["parts"][0]["sourceId"], "new-1")
            self.assertIsNone(checkpoint["threads"]["thread-3"]["parts"][1]["sourceId"])

            resumed_sources = FakeSources([failing.items[0]])
            by_id, by_title = sync.source_index(resumed_sources.items)
            result = await sync.sync_thread(FakeClient(resumed_sources), "notebook", thread, state, state_path, by_id, by_title, args())
            self.assertEqual(result["uploaded"], 1)
            self.assertEqual(result["reused"], 1)
            self.assertEqual(thread["uploadStatus"], "ready")

    def test_validate_state_rejects_visible_overflow(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projected = part(root / "one.md", "part")
            state = {
                "policyVersion": sync.REQUIRED_POLICY,
                "threads": {"bad": {"threadId": "bad", "policyVersion": sync.REQUIRED_POLICY, "stats": {"overflowVisibleLines": 1}, "parts": [projected]}},
            }
            with self.assertRaisesRegex(ValueError, "oversized visible message"):
                sync.validate_state(state)

    def test_validate_state_rejects_cross_thread_title_and_source_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = part(root / "one.md", "colliding title", "shared-source")
            second = part(root / "two.md", "colliding title", "shared-source")
            state = {
                "policyVersion": sync.REQUIRED_POLICY,
                "threads": {
                    "one": {"threadId": "one", "policyVersion": sync.REQUIRED_POLICY, "stats": {}, "parts": [first]},
                    "two": {"threadId": "two", "policyVersion": sync.REQUIRED_POLICY, "stats": {}, "parts": [second]},
                },
            }
            with self.assertRaisesRegex(ValueError, "Duplicate projected source title"):
                sync.validate_state(state)

            second["title"] = "unique title"
            with self.assertRaisesRegex(ValueError, "assigned to multiple projected parts"):
                sync.validate_state(state)

    def test_known_lineage_includes_current_and_previous_sources_only(self):
        state = {
            "threads": {
                "a": {
                    "parts": [{"sourceId": "current"}, {"sourceId": None}],
                    "previousSources": [{"sourceId": "previous"}],
                }
            }
        }
        self.assertEqual(sync.known_lineage_source_ids(state), {"current", "previous"})

    def test_duplicate_live_source_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate live source id"):
            sync.source_index([FakeSource("same", "a"), FakeSource("same", "b")])


if __name__ == "__main__":
    unittest.main()
