from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from unittest import mock
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
        source = FakeSource(f"new-{self.add_calls}", kwargs["title"])
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
    def test_atomic_json_retries_transient_windows_permission_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.json"
            real_replace = sync.os.replace
            attempts = 0

            def flaky_replace(source, destination):
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise PermissionError("simulated transient lock")
                return real_replace(source, destination)

            with mock.patch.object(sync.os, "replace", side_effect=flaky_replace):
                sync.atomic_json(target, {"ok": True})
            self.assertEqual(attempts, 3)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})

    def test_source_capacity_boundaries(self):
        sync.ensure_source_capacity(299, 1, 300)
        with self.assertRaisesRegex(ValueError, "Source cap would be exceeded"):
            sync.ensure_source_capacity(299, 2, 300)

    def test_provider_title_equivalence_allows_only_one_trailing_character_with_lineage(self):
        thread_id = "019f7082-1111-7111-8111-111111111111"
        expected = f"Codex ads-pc | {thread_id} | r0002 p1/1 | title"
        self.assertTrue(sync.provider_title_equivalent(expected, expected[:-1], thread_id))
        self.assertFalse(sync.provider_title_equivalent(expected, expected[:-2], thread_id))
        self.assertFalse(sync.provider_title_equivalent(expected, expected.replace("title", "xitle"), thread_id))
        self.assertFalse(sync.provider_title_equivalent(expected, expected[:-1], "different-thread"))

    def test_sequential_swap_peak_counts_shared_old_sources_once(self):
        old = FakeSource("shared", "old collision")
        threads = [
            {"threadId": "one", "parts": [{"title": "new one", "sourceId": None}], "previousSources": [{"sourceId": "shared", "title": "old collision"}]},
            {"threadId": "two", "parts": [{"title": "new two", "sourceId": None}], "previousSources": [{"sourceId": "shared", "title": "old collision"}]},
        ]
        plan = sync.planned_source_peak(threads, [old], swap_old=True)
        self.assertEqual(plan, {"existing": 1, "plannedNew": 2, "projectedPeak": 2, "projectedFinal": 2})
        retained = sync.planned_source_peak(threads, [old], swap_old=False)
        self.assertEqual(retained["projectedPeak"], 3)
        self.assertEqual(retained["projectedFinal"], 3)

    def test_duplicate_cross_task_titles_and_source_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate projected source title"):
            sync.validate_unique_current_lineage([
                {"threadId": "one", "parts": [{"title": "same", "sourceId": None}]},
                {"threadId": "two", "parts": [{"title": "same", "sourceId": None}]},
            ])

    def test_known_orphans_accepts_only_unreferenced_prior_lineage_titles(self):
        referenced = FakeSource("old-1", "old title")
        orphan = FakeSource("orphan", "old title")
        thread = {"threadId": "one", "parts": [{"title": "new", "sourceId": None}], "previousSources": [{"sourceId": "old-1", "title": "old title"}]}
        self.assertEqual(sync.known_orphans([thread], [referenced, orphan]), [orphan])
        with self.assertRaisesRegex(ValueError, "unrecognized live source"):
            sync.known_orphans([thread], [referenced, FakeSource("foreign", "foreign title")])

    def test_exact_notebook_scope_rejects_missing_extra_and_duplicate_ids(self):
        threads = [{"threadId": "one", "parts": [{"sourceId": "one", "title": "one"}]}]
        sync.validate_exact_notebook_scope(threads, [FakeSource("one", "one")])
        with self.assertRaisesRegex(ValueError, "source-set mismatch"):
            sync.validate_exact_notebook_scope(threads, [FakeSource("one", "one"), FakeSource("extra", "extra")])
        with self.assertRaisesRegex(ValueError, "duplicate IDs"):
            sync.validate_exact_notebook_scope([{"threadId": "dup", "parts": [{"sourceId": "one"}, {"sourceId": "one"}]}], [FakeSource("one", "one")])
        with self.assertRaisesRegex(ValueError, "Duplicate projected source ID"):
            sync.validate_unique_current_lineage([
                {"threadId": "one", "parts": [{"title": "one", "sourceId": "shared"}]},
                {"threadId": "two", "parts": [{"title": "two", "sourceId": "shared"}]},
            ])

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


if __name__ == "__main__":
    unittest.main()
