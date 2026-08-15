#!/usr/bin/env python3
"""Run independent development or holdout temporal validation cases.

The fixture contains expected logical labels, while the runner constructs
production-shaped event identities and a temporary SQLite index. Reports keep
only aggregate counts and digests so benchmark evidence does not copy message
content into the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import thread_temporal_context as context  # noqa: E402
import thread_temporal_index as index  # noqa: E402


CONTRACT = "temporal-validation-suite-v1"


class ValidationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError("SUITE_INVALID", f"cannot read suite: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValidationError("SUITE_INVALID", "suite root must be an object")
    return value


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def event_records(suite: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    raw_events = suite.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise ValidationError("SUITE_INVALID", "events must be a non-empty array")
    records: list[dict[str, Any]] = []
    event_to_logical: dict[str, str] = {}
    for line, raw in enumerate(raw_events, start=2):
        if not isinstance(raw, dict):
            raise ValidationError("SUITE_INVALID", "event entries must be objects")
        logical_id = str(raw.get("logicalId") or "")
        thread_id = str(raw.get("threadId") or "")
        role = str(raw.get("role") or "")
        timestamp = str(raw.get("timestamp") or "")
        text = str(raw.get("text") or "")
        if not all((logical_id, thread_id, role, timestamp, text)):
            raise ValidationError("SUITE_INVALID", "event is missing required fixture fields")
        event_id = index.sha256("\x00".join([thread_id, role, timestamp, text]))
        if event_id in event_to_logical:
            raise ValidationError("SUITE_INVALID", "fixture event identity is duplicated")
        event_to_logical[event_id] = logical_id
        records.append(
            {
                "recordType": "event",
                "contractVersion": "temporal-event-v1",
                "eventId": event_id,
                "threadId": thread_id,
                "role": role,
                "timestampUtc": timestamp,
                "text": text,
                "textDigest": sha256_text(text),
                "sourceRef": {"sourceKind": "active", "sourceFileDigest": "val-001-fixture", "lineNumber": line},
            }
        )
    return records, event_to_logical


def write_handoff(path: Path, records: list[dict[str, Any]], suite_digest: str) -> None:
    header = {
        "recordType": "header",
        "contractVersion": "temporal-event-v1",
        "policyVersion": "visible-messages-secrets-redacted-v4",
        "generatedAt": "2026-08-14T00:00:00.000Z",
        "threadCount": len({record["threadId"] for record in records}),
        "manifestDigest": suite_digest,
    }
    lines = [json.dumps(header, separators=(",", ":"), ensure_ascii=False) + "\n"]
    event_digest = hashlib.sha256()
    for record in records:
        line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
        lines.append(line)
        event_digest.update(line.encode("utf-8"))
    trailer = {
        "recordType": "trailer",
        "contractVersion": "temporal-event-v1",
        "eventCount": len(records),
        "quarantineCount": 0,
        "malformedLines": 0,
        "overflowLines": 0,
        "overflowVisibleLines": 0,
        "duplicateMessages": 0,
        "eventDigest": event_digest.hexdigest(),
    }
    lines.append(json.dumps(trailer, separators=(",", ":"), ensure_ascii=False) + "\n")
    path.write_text("".join(lines), encoding="utf-8", newline="\n")


def resolve_case(case: dict[str, Any], node_path: str) -> tuple[dict[str, Any] | None, str | None]:
    command = [node_path, str(SCRIPT_DIR / "thread_temporal_resolve.mjs"), "--timezone", str(case.get("timezone") or "America/New_York")]
    if case.get("now"):
        command.extend(["--now", str(case["now"])])
    if case.get("weekStart"):
        command.extend(["--week-start", str(case["weekStart"])])
    if case.get("expression"):
        command.extend(["--expression", str(case["expression"])])
    else:
        command.extend(["--start", str(case.get("start") or ""), "--end", str(case.get("end") or "")])
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
    output = completed.stdout.strip() or completed.stderr.strip()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return None, "RESOLVER_MALFORMED"
    if completed.returncode != 0:
        return None, str(payload.get("code") or "RESOLVER_ERROR")
    return payload, None


def run_case(case: dict[str, Any], database: Path, event_to_logical: dict[str, str], node_path: str) -> dict[str, Any]:
    case_id = str(case.get("id") or "")
    expected_error = str(case.get("expectedErrorCode") or "")
    resolved, error_code = resolve_case(case, node_path)
    if expected_error:
        passed = error_code == expected_error
        return {"id": case_id, "passed": passed, "resolverError": error_code, "expectedError": expected_error, "actualCount": 0, "expectedCount": 0}
    if error_code or resolved is None:
        return {"id": case_id, "passed": False, "resolverError": error_code or "RESOLVER_EMPTY", "actualCount": 0, "expectedCount": len(case.get("expectedLogicalIds") or [])}

    expected_start = case.get("expectedStartUtc")
    expected_end = case.get("expectedEndUtc")
    range_matches = (expected_start in {None, resolved.get("startUtc")} and expected_end in {None, resolved.get("endUtc")})
    start = str(resolved.get("startUtc") or "")
    end = str(resolved.get("endUtc") or "")
    actual_events = index.query_events(database, start, end)
    actual_logical = [event_to_logical[event["eventId"]] for event in actual_events]
    expected_logical = [str(value) for value in case.get("expectedLogicalIds") or []]
    context_result = context.build_context(database, start, end, str(case.get("timezone") or "America/New_York"), mode="deep", node_path=node_path)
    context_logical = [event_to_logical[event["eventId"]] for event in context_result.get("messages") or []]
    passed = range_matches and actual_logical == expected_logical and context_logical == expected_logical
    return {
        "id": case_id,
        "passed": passed,
        "resolverError": None,
        "rangeMatches": range_matches,
        "contextStatus": context_result.get("status"),
        "actualCount": len(actual_logical),
        "expectedCount": len(expected_logical),
        "contextCount": len(context_logical),
    }


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic temporal development or holdout validation cases.")
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--set", choices=("development", "holdout"), required=True)
    parser.add_argument("--node", default="node")
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = parse_args(argv or sys.argv[1:])
    try:
        suite = read_json(args.suite.resolve())
        records, event_to_logical = event_records(suite)
        selected_cases = suite.get(f"{args.set}Cases")
        if not isinstance(selected_cases, list) or not selected_cases:
            raise ValidationError("SUITE_INVALID", f"{args.set}Cases must be a non-empty array")
        suite_digest = hashlib.sha256(json.dumps(suite, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        with tempfile.TemporaryDirectory(prefix="codex-temporal-validation-") as temporary:
            root = Path(temporary)
            handoff = root / "events.ndjson"
            database = root / "temporal.sqlite3"
            write_handoff(handoff, records, suite_digest)
            index_result = index.build_index(handoff, database, rebuild=True)
            results = [run_case(case, database, event_to_logical, args.node) for case in selected_cases]
        compact_results = [
            {key: value for key, value in result.items() if key in {"id", "passed", "actualCount", "expectedCount", "contextCount", "contextStatus", "rangeMatches", "resolverError", "expectedError"}}
            for result in results
        ]
        result_digest = hashlib.sha256(json.dumps(compact_results, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        payload = {
            "contractVersion": CONTRACT,
            "suite": str(args.set),
            "suiteDigest": suite_digest,
            "eventCount": len(records),
            "indexEventCount": index_result.get("eventCount"),
            "caseCount": len(results),
            "passedCases": sum(bool(result["passed"]) for result in results),
            "failedCases": sum(not bool(result["passed"]) for result in results),
            "resultDigest": result_digest,
            "cases": compact_results,
        }
        atomic_json(args.out.resolve(), payload)
        print(json.dumps({"status": "ok" if payload["failedCases"] == 0 else "failed", "suite": args.set, "caseCount": payload["caseCount"], "passedCases": payload["passedCases"], "failedCases": payload["failedCases"], "resultDigest": result_digest, "out": str(args.out.resolve())}))
        return 0 if payload["failedCases"] == 0 else 1
    except (ValidationError, index.TemporalIndexError, context.TemporalContextError) as exc:
        print(json.dumps({"status": "error", "code": getattr(exc, "code", "VALIDATION_ERROR"), "message": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
