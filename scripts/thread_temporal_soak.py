#!/usr/bin/env python3
"""Run an accelerated local soak of the temporal refresh/promote boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import thread_temporal_refresh as refresh  # noqa: E402
import thread_temporal_index as index  # noqa: E402


def _event(text: str, stamp: str) -> dict:
    event = {
        "recordType": "event",
        "contractVersion": "temporal-event-v1",
        "threadId": "soak-thread",
        "role": "user",
        "timestampUtc": stamp,
        "text": text,
        "textDigest": hashlib.sha256(text.encode()).hexdigest(),
        "sourceRef": {
            "sourceKind": "active",
            "sourceFileDigest": "soak-source",
            "lineNumber": 1,
        },
    }
    event["eventId"] = hashlib.sha256(
        "\x00".join([event["threadId"], event["role"], event["timestampUtc"], text]).encode()
    ).hexdigest()
    return event


def write_handoff(path: Path, cycle: int, quarantine: bool = False) -> None:
    stamp = (datetime(2026, 1, 1, 12, tzinfo=UTC) + timedelta(minutes=cycle)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    events = [_event(f"soak cycle {cycle}", stamp)]
    event_line = json.dumps(events[0], separators=(",", ":")) + "\n"
    rows = [
        {
            "recordType": "header",
            "contractVersion": "temporal-event-v1",
            "policyVersion": "visible-messages-secrets-redacted-v4",
            "generatedAt": "2026-01-01T00:00:00.000Z",
            "threadCount": 1,
            "manifestDigest": f"soak-manifest-{cycle}",
        },
        events[0],
    ]
    if quarantine:
        rows.append(
            {
                "recordType": "quarantine",
                "contractVersion": "temporal-event-v1",
                "threadId": "soak-thread",
                "reason": "missing-timestamp",
                "sourceRef": {
                    "sourceKind": "active",
                    "sourceFileDigest": "soak-source",
                    "lineNumber": 2,
                },
            }
        )
    rows.append(
        {
            "recordType": "trailer",
            "contractVersion": "temporal-event-v1",
            "eventCount": 1,
            "quarantineCount": int(quarantine),
            "malformedLines": 0,
            "overflowLines": 0,
            "overflowVisibleLines": 0,
            "duplicateMessages": 0,
            "eventDigest": hashlib.sha256(event_line.encode()).hexdigest(),
        }
    )
    path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def run(cycles: int) -> dict:
    if cycles < 3:
        raise ValueError("cycles must be at least 3")
    with tempfile.TemporaryDirectory(prefix="codex-temporal-soak-") as temporary:
        root = Path(temporary)
        state = root / "state.json"
        state.write_text(
            json.dumps({"policyVersion": index.POLICY, "threads": {"soak-thread": {}}}),
            encoding="utf-8",
        )
        source = root / "source.jsonl"
        source.write_text("stable source\n", encoding="utf-8")
        fixture_handoff = root / "fixture.ndjson"
        current_cycle = {"value": 0, "quarantine": False}

        def fake_child(_executable, arguments, _label, _timeout):
            output = Path(arguments[arguments.index("--out") + 1])
            if "--state" in arguments:
                output.write_text(
                    json.dumps(
                        {
                            "threadCount": 1,
                            "missingThreadCount": 0,
                            "threads": [{"id": "soak-thread", "path": str(source), "updatedAt": 1}],
                        }
                    ),
                    encoding="utf-8",
                )
            else:
                write_handoff(output, current_cycle["value"], current_cycle["quarantine"])

        successful = 0
        changed = 0
        digests: list[str] = []
        recovery_pass = False
        fail_closed_pass = False
        staging_leaks = 0
        for cycle in range(1, cycles + 1):
            current_cycle["value"] = cycle
            current_cycle["quarantine"] = False
            if cycle == max(2, cycles // 2):
                (root / "temporal" / "temporal.sqlite3").write_bytes(b"intentional corruption")
            with patch.object(refresh, "_run_child", side_effect=fake_child):
                result = refresh.refresh(state_path=state, root=root / "temporal", node_path="fixture")
            successful += int(result["status"] == "ok")
            changed += int(result["changed"])
            recovery_pass = recovery_pass or bool(result["recoveredCurrentIndex"])
            digests.append(str(result["eventDigest"]))
            staging_leaks += len(list((root / "temporal").glob(".temporal-refresh-*")))

            if cycle == max(2, cycles // 2) + 1:
                current_cycle["quarantine"] = True
                before = index.verify_database(root / "temporal" / "temporal.sqlite3")["eventDigest"]
                with patch.object(refresh, "_run_child", side_effect=fake_child):
                    try:
                        refresh.refresh(state_path=state, root=root / "temporal", node_path="fixture")
                    except refresh.TemporalRefreshError as exc:
                        fail_closed_pass = exc.code == "SOURCE_DIAGNOSTICS"
                after = index.verify_database(root / "temporal" / "temporal.sqlite3")["eventDigest"]
                fail_closed_pass = fail_closed_pass and before == after

        verified = index.verify_database(root / "temporal" / "temporal.sqlite3")
        return {
            "status": "pass"
            if successful == cycles and recovery_pass and fail_closed_pass and staging_leaks == 0 and verified["quarantineCount"] == 0
            else "fail",
            "cycles": cycles,
            "successfulCycles": successful,
            "changedCycles": changed,
            "uniqueEventDigests": len(set(digests)),
            "recoveryPass": recovery_pass,
            "failClosedPass": fail_closed_pass,
            "stagingLeakCount": staging_leaks,
            "finalEventCount": verified["eventCount"],
            "finalQuarantineCount": verified["quarantineCount"],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=14)
    parser.add_argument("--out", type=Path, help="optional aggregate JSON result path")
    args = parser.parse_args()
    try:
        result = run(args.cycles)
    except (OSError, ValueError, refresh.TemporalRefreshError) as exc:
        print(json.dumps({"status": "error", "code": type(exc).__name__}, separators=(",", ":")))
        return 1
    if args.out:
        args.out.resolve().parent.mkdir(parents=True, exist_ok=True)
        temporary = args.out.resolve().with_name(f".{args.out.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
        temporary.replace(args.out.resolve())
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
