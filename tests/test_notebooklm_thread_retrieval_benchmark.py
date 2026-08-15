from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "notebooklm_thread_retrieval_benchmark.py"
SPEC = importlib.util.spec_from_file_location("notebooklm_thread_retrieval_benchmark", MODULE_PATH)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark)


class RetrievalBenchmarkTests(unittest.TestCase):
    def test_parser_defaults_transport_retries_to_zero(self):
        with patch(
            "sys.argv",
            [
                "benchmark",
                "--state", "state.json",
                "--cases", "cases.json",
                "--profile", "personal",
                "--notebook-id", "notebook",
                "--confirm-disposable-retrieval-notebook",
            ],
        ):
            args = benchmark.parse_args()
        self.assertEqual(args.transport_max_retries, 0)

    def test_make_client_passes_explicit_transport_retry_budget(self):
        args = SimpleNamespace(profile="personal", transport_max_retries=0)
        with patch.object(benchmark.NotebookLMClient, "from_storage", return_value="client") as factory:
            self.assertEqual(benchmark.make_client(args), "client")
        factory.assert_called_once_with(
            profile="personal",
            chat_timeout=240.0,
            rate_limit_max_retries=0,
            server_error_max_retries=0,
        )


if __name__ == "__main__":
    unittest.main()
