#!/usr/bin/env python3
"""Measure no-op and one-thread-append temporal index latency.

The benchmark uses synthetic events and reports only aggregate timings.  It
checks the release floors from the temporal plan: no-change P95 <= 1 second
and one-thread append P95 <= 2 seconds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import thread_temporal_index as temporal_index  # noqa: E402


CONTRACT = "temporal-incremental-benchmark-v1"


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def event(thread_number: int, event_number: int) -> dict[str, Any]:
    thread_id = f"incremental-thread-{thread_number:05d}"
    timestamp = f"2026-01-{(event_number % 28) + 1:02d}T{(event_number % 24):02d}:{(thread_number % 60):02d}:00.000Z"
    text = f"synthetic incremental event {thread_number}:{event_number}"
    event_id = temporal_index.sha256("\x00".join([thread_id, "user", timestamp, text]))
    return {
        "recordType": "event",
        "contractVersion": temporal_index.CONTRACT,
        "eventId": event_id,
        "threadId": thread_id,
        "role": "user",
        "timestampUtc": timestamp,
        "text": text,
        "textDigest": temporal_index.sha256(text),
        "sourceRef": {
            "sourceKind": "active",
            "sourceFileDigest": temporal_index.sha256(thread_id),
            "lineNumber": event_number + 1,
        },
    }


def write_handoff(path: Path, events: list[dict[str, Any]], manifest: str) -> None:
    header = {
        "recordType": "header",
        "contractVersion": temporal_index.CONTRACT,
        "policyVersion": temporal_index.POLICY,
        "generatedAt": "2026-01-01T00:00:00.000Z",
        "threadCount": len({item["threadId"] for item in events}),
        "manifestDigest": temporal_index.sha256(manifest),
    }
    digest = hashlib.sha256()
    lines = [json.dumps(header, separators=(",", ":"), ensure_ascii=False) + "\n"]
    for item in events:
        line = json.dumps(item, separators=(",", ":"), ensure_ascii=False) + "\n"
        lines.append(line)
        digest.update(line.encode("utf-8"))
    lines.append(json.dumps({
        "recordType": "trailer",
        "contractVersion": temporal_index.CONTRACT,
        "eventCount": len(events),
        "quarantineCount": 0,
        "malformedLines": 0,
        "overflowLines": 0,
        "overflowVisibleLines": 0,
        "duplicateMessages": 0,
        "eventDigest": digest.hexdigest(),
    }, separators=(",", ":")) + "\n")
    path.write_text("".join(lines), encoding="utf-8", newline="\n")


def measure_build(handoff: Path, database: Path) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    result = temporal_index.build_index(handoff, database)
    return result, (time.perf_counter() - started) * 1000


def run_incremental(*, threads: int, events_per_thread: int, repeats: int) -> dict[str, Any]:
    if min(threads, events_per_thread, repeats) < 1:
        raise ValueError("benchmark dimensions must be positive")
    with tempfile.TemporaryDirectory(prefix="codex-temporal-incremental-") as temporary:
        root = Path(temporary)
        database = root / "temporal.sqlite3"
        base = [event(thread_number, event_number) for thread_number in range(threads) for event_number in range(events_per_thread)]
        baseline = root / "baseline.ndjson"
        write_handoff(baseline, base, "baseline")
        first = temporal_index.build_index(baseline, database, rebuild=True)

        no_change_times: list[float] = []
        no_ops = 0
        for _ in range(repeats):
            result, elapsed = measure_build(baseline, database)
            no_change_times.append(elapsed)
            no_ops += int(bool(result.get("noOp")))

        append_times: list[float] = []
        changed = 0
        final_count = int(first.get("eventCount") or 0)
        for iteration in range(repeats):
            appended = [*base, event(threads, iteration)]
            handoff = root / f"append-{iteration}.ndjson"
            write_handoff(handoff, appended, f"append-{iteration}")
            result, elapsed = measure_build(handoff, database)
            append_times.append(elapsed)
            changed += int(bool(result.get("changed")))
            final_count = int(result.get("eventCount") or 0)
            base = appended

        no_change_p95 = percentile(no_change_times, 0.95)
        append_p95 = percentile(append_times, 0.95)
        return {
            "contractVersion": CONTRACT,
            "status": "pass" if no_ops == repeats and changed == repeats and no_change_p95 <= 1000 and append_p95 <= 2000 else "fail",
            "threads": threads,
            "initialEventCount": threads * events_per_thread,
            "repeats": repeats,
            "noChange": {
                "noOpCount": no_ops,
                "p50Ms": round(percentile(no_change_times, 0.50), 3),
                "p95Ms": round(no_change_p95, 3),
                "floorMs": 1000,
                "floorPass": no_ops == repeats and no_change_p95 <= 1000,
            },
            "oneThreadAppend": {
                "changedCount": changed,
                "p50Ms": round(percentile(append_times, 0.50), 3),
                "p95Ms": round(append_p95, 3),
                "floorMs": 2000,
                "floorPass": changed == repeats and append_p95 <= 2000,
                "finalEventCount": final_count,
            },
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, default=145)
    parser.add_argument("--events-per-thread", type=int, default=16)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv or sys.argv[1:])
    try:
        result = run_incremental(threads=args.threads, events_per_thread=args.events_per_thread, repeats=args.repeats)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.out.with_name(f".{args.out.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
        temporary.replace(args.out)
        print(json.dumps({"status": result["status"], "out": str(args.out.resolve()), "noChangeP95Ms": result["noChange"]["p95Ms"], "appendP95Ms": result["oneThreadAppend"]["p95Ms"]}, separators=(",", ":")))
        return 0 if result["status"] == "pass" else 1
    except (OSError, ValueError, temporal_index.TemporalIndexError) as exc:
        print(json.dumps({"status": "error", "code": type(exc).__name__}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
