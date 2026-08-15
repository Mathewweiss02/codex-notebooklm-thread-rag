#!/usr/bin/env python3
"""Measure local temporal-index correctness and latency at bounded synthetic scale.

This benchmark uses generated events only.  It compares every indexed query
result with a deliberately simple in-memory oracle and emits aggregate timing
and memory-allocation evidence without writing message text or local paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import thread_temporal_index as temporal_index  # noqa: E402


CONTRACT = "temporal-scale-benchmark-v1"
POLICY = temporal_index.POLICY


def event(thread_number: int, event_number: int) -> dict[str, Any]:
    thread_id = f"synthetic-thread-{thread_number:05d}"
    timestamp = f"2026-01-{(event_number % 28) + 1:02d}T{(event_number % 24):02d}:{(thread_number % 60):02d}:00.000Z"
    text = f"synthetic event {thread_number}:{event_number}"
    event_id = temporal_index.sha256("\x00".join([thread_id, "user", timestamp, text]))
    return {
        "recordType": "event",
        "contractVersion": "temporal-event-v1",
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


def write_handoff(path: Path, thread_count: int, events_per_thread: int) -> list[dict[str, Any]]:
    events = [event(thread_number, event_number) for thread_number in range(thread_count) for event_number in range(events_per_thread)]
    header = {
        "recordType": "header",
        "contractVersion": "temporal-event-v1",
        "policyVersion": POLICY,
        "generatedAt": "2026-01-01T00:00:00.000Z",
        "threadCount": thread_count,
        "manifestDigest": temporal_index.sha256(f"synthetic:{thread_count}:{events_per_thread}"),
    }
    event_digest = hashlib.sha256()
    lines = [json.dumps(header, separators=(",", ":"), ensure_ascii=False) + "\n"]
    for item in events:
        line = json.dumps(item, separators=(",", ":"), ensure_ascii=False) + "\n"
        lines.append(line)
        event_digest.update(line.encode("utf-8"))
    trailer = {
        "recordType": "trailer",
        "contractVersion": "temporal-event-v1",
        "eventCount": len(events),
        "quarantineCount": 0,
        "malformedLines": 0,
        "overflowLines": 0,
        "overflowVisibleLines": 0,
        "duplicateMessages": 0,
        "eventDigest": event_digest.hexdigest(),
    }
    lines.append(json.dumps(trailer, separators=(",", ":"), ensure_ascii=False) + "\n")
    path.write_text("".join(lines), encoding="utf-8", newline="\n")
    return events


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def run_scale(*, multipliers: list[int], base_threads: int, events_per_thread: int, repeats: int) -> dict[str, Any]:
    if not multipliers or any(value < 1 for value in multipliers):
        raise ValueError("multipliers must be positive")
    if base_threads < 1 or events_per_thread < 1 or repeats < 1:
        raise ValueError("benchmark dimensions must be positive")
    rows: list[dict[str, Any]] = []
    correctness = True
    with tempfile.TemporaryDirectory(prefix="codex-temporal-scale-") as temporary:
        root = Path(temporary)
        for multiplier in sorted(set(multipliers)):
            thread_count = base_threads * multiplier
            handoff = root / f"handoff-{multiplier}.ndjson"
            database = root / f"index-{multiplier}.sqlite3"
            events = write_handoff(handoff, thread_count, events_per_thread)
            query_start = "2026-01-01T00:00:00.000Z"
            query_end = "2026-02-01T00:00:00.000Z"
            oracle_ids = {
                str(item["eventId"])
                for item in events
                if query_start <= str(item["timestampUtc"]) < query_end
            }
            tracemalloc.start()
            started = time.perf_counter()
            built = temporal_index.build_index(handoff, database, rebuild=True)
            build_ms = (time.perf_counter() - started) * 1000
            _current, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            query_times: list[float] = []
            result_counts: list[int] = []
            result_digest = ""
            for _ in range(repeats):
                started = time.perf_counter()
                result = temporal_index.query_events(database, query_start, query_end)
                query_times.append((time.perf_counter() - started) * 1000)
                result_counts.append(len(result))
                result_digest = hashlib.sha256(
                    "\n".join(str(item["eventId"]) for item in result).encode("utf-8")
                ).hexdigest()
                if {str(item["eventId"]) for item in result} != oracle_ids:
                    correctness = False
            rows.append({
                "multiplier": multiplier,
                "threadCount": thread_count,
                "eventCount": len(events),
                "indexedEventCount": int(built.get("eventCount") or 0),
                "oracleEventCount": len(oracle_ids),
                "queryResultCounts": result_counts,
                "correctness": result_counts == [len(oracle_ids)] * repeats,
                "buildMs": round(build_ms, 3),
                "queryP50Ms": round(percentile(query_times, 0.50), 3),
                "queryP95Ms": round(percentile(query_times, 0.95), 3),
                "peakPythonAllocBytes": int(peak_bytes),
                "resultDigest": result_digest,
            })
    return {
        "contractVersion": CONTRACT,
        "status": "pass" if correctness and all(row["correctness"] for row in rows) else "fail",
        "multipliers": sorted(set(multipliers)),
        "baseThreads": base_threads,
        "eventsPerThread": events_per_thread,
        "repeats": repeats,
        "rows": rows,
        "correctness": correctness,
    }


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--multipliers", nargs="+", type=int, default=[1, 2, 5, 10])
    parser.add_argument("--base-threads", type=int, default=12)
    parser.add_argument("--events-per-thread", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv or sys.argv[1:])
    try:
        result = run_scale(
            multipliers=args.multipliers,
            base_threads=args.base_threads,
            events_per_thread=args.events_per_thread,
            repeats=args.repeats,
        )
        atomic_json(args.out.resolve(), result)
        print(json.dumps({"status": result["status"], "multipliers": result["multipliers"], "out": str(args.out.resolve())}, separators=(",", ":")))
        return 0 if result["status"] == "pass" else 1
    except (OSError, ValueError, temporal_index.TemporalIndexError) as exc:
        print(json.dumps({"status": "error", "code": type(exc).__name__}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
