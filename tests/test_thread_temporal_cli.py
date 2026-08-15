from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import thread_temporal_index as index  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "thread_temporal_cli.py"


def event(thread_id: str, timestamp: str, text: str, line: int) -> dict[str, object]:
    event_id = index.sha256("\x00".join([thread_id, "user", timestamp, text]))
    return {
        "recordType": "event",
        "contractVersion": "temporal-event-v1",
        "eventId": event_id,
        "threadId": thread_id,
        "role": "user",
        "timestampUtc": timestamp,
        "text": text,
        "textDigest": index.sha256(text),
        "sourceRef": {"sourceKind": "active", "sourceFileDigest": "fixture-cli", "lineNumber": line},
    }


def write_handoff(path: Path, events: list[dict[str, object]], thread_metadata: dict[str, dict[str, object]] | None = None) -> None:
    header = {
        "recordType": "header",
        "contractVersion": "temporal-event-v1",
        "policyVersion": "visible-messages-secrets-redacted-v4",
        "generatedAt": "2026-08-14T00:00:00.000Z",
        "threadCount": len({event["threadId"] for event in events}),
        "manifestDigest": "fixture-cli-manifest",
    }
    if thread_metadata is not None:
        header["threadMetadata"] = thread_metadata
    lines = [json.dumps(header, separators=(",", ":")) + "\n"]
    event_digest = hashlib.sha256()
    for record in events:
        line = json.dumps(record, separators=(",", ":")) + "\n"
        lines.append(line)
        event_digest.update(line.encode("utf-8"))
    lines.append(json.dumps({
        "recordType": "trailer",
        "contractVersion": "temporal-event-v1",
        "eventCount": len(events),
        "quarantineCount": 0,
        "malformedLines": 0,
        "overflowLines": 0,
        "overflowVisibleLines": 0,
        "duplicateMessages": 0,
        "eventDigest": event_digest.hexdigest(),
    }, separators=(",", ":")) + "\n")
    path.write_text("".join(lines), encoding="utf-8")


class TemporalCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = [
            event("thread-a", "2026-02-02T04:00:00.000Z", "refactor — temporal memory", 1),
            event("thread-a", "2026-02-02T05:00:00.000Z", "test the notebook context", 2),
            event("thread-b", "2026-02-03T12:00:00.000Z", "unrelated work", 3),
        ]

    def run_cli(self, database: Path | None, *arguments: str, expected_code: int = 0) -> dict[str, object]:
        command = [sys.executable, str(CLI)]
        if database is not None:
            command.extend(["--node", "node"])
        command.extend(arguments)
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False, timeout=30)
        self.assertEqual(completed.returncode, expected_code, completed.stderr or completed.stdout)
        return json.loads(completed.stdout)

    def build_database(self, root: Path) -> Path:
        handoff = root / "handoff.jsonl"
        database = root / "temporal.sqlite3"
        write_handoff(handoff, self.events)
        index.build_index(handoff, database, rebuild=True)
        return database

    def test_when_recap_find_and_compare_share_one_resolved_contract(self) -> None:
        when = self.run_cli(None, "when", "--expression", "2026-02-02", "--timezone", "UTC", "--now", "2026-02-04T12:00:00.000Z")
        self.assertEqual(when["contractVersion"], "temporal-cli-v1")
        self.assertEqual(when["result"]["startUtc"], "2026-02-02T00:00:00.000Z")

        with tempfile.TemporaryDirectory() as temporary:
            database = self.build_database(Path(temporary))
            recap = self.run_cli(database, "recap", "--db", str(database), "--expression", "2026-02-02", "--timezone", "UTC", "--now", "2026-02-04T12:00:00.000Z")
            found = self.run_cli(database, "find", "--db", str(database), "--expression", "2026-02-02", "--timezone", "UTC", "--now", "2026-02-04T12:00:00.000Z", "--query", "refactor")
            compared = self.run_cli(database, "compare", "--db", str(database), "--left", "2026-02-02", "--right", "2026-02-03", "--timezone", "UTC", "--now", "2026-02-04T12:00:00.000Z")

        self.assertEqual(recap["result"]["status"], "ok")
        self.assertEqual(recap["result"]["coverage"]["canonicalEventCount"], 2)
        self.assertEqual(found["result"]["coverage"]["matchedEventCount"], 1)
        self.assertEqual(compared["result"]["delta"]["leftOnlyCount"], 2)
        self.assertEqual(compared["result"]["delta"]["rightOnlyCount"], 1)

    def test_invalid_time_is_machine_readable_and_nonzero(self) -> None:
        result = self.run_cli(None, "when", "--start", "2026-02-03T00:00:00.000Z", "--end", "2026-02-02T00:00:00.000Z", "--timezone", "UTC", expected_code=1)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["code"], "INVALID_TIME_RANGE")

    def test_project_filter_is_available_through_the_primary_cli(self) -> None:
        metadata = {
            "thread-a": {"workspaceLabel": "Hermes", "workspaceHash": "hermes123", "archived": False, "source": "vscode"},
            "thread-b": {"workspaceLabel": "Other", "workspaceHash": "other456", "archived": False, "source": "vscode"},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "handoff.jsonl"
            database = root / "temporal.sqlite3"
            write_handoff(handoff, self.events, metadata)
            index.build_index(handoff, database, rebuild=True)
            result = self.run_cli(
                database,
                "recap",
                "--db", str(database),
                "--expression", "2026-02-02",
                "--timezone", "UTC",
                "--now", "2026-02-04T12:00:00.000Z",
                "--project", "Hermes",
            )
        self.assertEqual(result["result"]["selection"]["project"], "Hermes")
        self.assertEqual(result["result"]["projectFilter"]["matchedThreadIds"], ["thread-a"])
        self.assertTrue(all(message["threadId"] == "thread-a" for message in result["result"]["messages"]))

    def test_ambiguous_local_time_is_disclosed_instead_of_guessed(self) -> None:
        result = self.run_cli(
            None,
            "when",
            "--start",
            "2026-11-01 01:30",
            "--end",
            "2026-11-01 02:30",
            "--timezone",
            "America/New_York",
            expected_code=1,
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["code"], "AMBIGUOUS_LOCAL_TIME")
        self.assertIn("explicit UTC offset", result["message"])


if __name__ == "__main__":
    unittest.main()
