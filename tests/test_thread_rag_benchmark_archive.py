from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "thread_rag_benchmark_archive.py"
SPEC = importlib.util.spec_from_file_location("thread_rag_benchmark_archive", MODULE_PATH)
archive = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(archive)


class BenchmarkArchiveTests(unittest.TestCase):
    def test_immutable_copy_refuses_different_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            target = root / "target.json"
            source.write_text('{"a":1}', encoding="utf-8")
            target.write_text('{"a":2}', encoding="utf-8")
            with self.assertRaises(FileExistsError):
                archive.copy_immutable(source, target)

    def test_immutable_copy_is_idempotent_for_same_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            target = root / "target.json"
            source.write_text(json.dumps({"a": 1}), encoding="utf-8")
            first = archive.copy_immutable(source, target)
            second = archive.copy_immutable(source, target)
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
