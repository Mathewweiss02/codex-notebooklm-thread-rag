from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skill" / "codex-notebooklm-thread-rag" / "SKILL.md"
ROUTING = ROOT / "skill" / "codex-notebooklm-thread-rag" / "references" / "temporal-routing.json"
REFERENCE = ROOT / "skill" / "codex-notebooklm-thread-rag" / "references" / "temporal-memory.md"


class TemporalSkillRoutingTests(unittest.TestCase):
    def test_route_table_and_skill_agree_on_broad_temporal_precedence(self) -> None:
        skill_text = SKILL.read_text(encoding="utf-8")
        reference_text = REFERENCE.read_text(encoding="utf-8")
        routing = json.loads(ROUTING.read_text(encoding="utf-8"))

        self.assertIn("thread_temporal_cli.py", skill_text)
        self.assertIn("Do not route these requests to semantic-only NotebookLM search", skill_text)
        self.assertIn("references/temporal-routing.json", skill_text)
        for route in routing["routes"].values():
            self.assertIn(route.split(" ", 1)[0], reference_text)
        for invariant in routing["invariants"]:
            self.assertTrue(invariant)

    def test_every_cold_start_signal_has_a_local_route(self) -> None:
        routing = json.loads(ROUTING.read_text(encoding="utf-8"))
        route_text = " ".join(routing["routes"].values())
        for signal in routing["broadTemporalSignals"]:
            self.assertTrue(signal)
            self.assertIn("thread_temporal_cli.py", route_text)

    def test_cold_start_cases_have_expected_command_and_temporal_cases_are_local(self) -> None:
        routing = json.loads(ROUTING.read_text(encoding="utf-8"))
        for case in routing["coldStartCases"]:
            expected = case["expectedRoute"]
            self.assertIn(expected, " ".join(routing["routes"].values()))
            if "thread_temporal_cli.py" in expected:
                self.assertNotIn("notebooklm_thread_search.py", expected)

    def test_exact_period_question_stays_local_without_remote_latency(self) -> None:
        routing = json.loads(ROUTING.read_text(encoding="utf-8"))
        exact_case = next(case for case in routing["coldStartCases"] if case["prompt"] == "What was I doing yesterday?")
        self.assertEqual(exact_case["expectedRoute"], "thread_temporal_cli.py recap")
        self.assertIn("broad temporal requests route to local temporal CLI before semantic search", routing["invariants"])
        self.assertNotIn("notebooklm_thread_search.py", exact_case["expectedRoute"])


if __name__ == "__main__":
    unittest.main()
