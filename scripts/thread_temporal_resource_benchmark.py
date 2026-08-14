#!/usr/bin/env python3
"""Measure repeated local temporal queries for correctness and resource growth."""

from __future__ import annotations

import argparse
import ctypes
import gc
import hashlib
import json
import os
import statistics
import sys
import tempfile
import time
import tracemalloc
from ctypes import wintypes
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import thread_temporal_index as temporal_index  # noqa: E402
from thread_temporal_scale_benchmark import write_handoff  # noqa: E402


CONTRACT = "temporal-resource-benchmark-v1"
PEAK_MEMORY_LIMIT_BYTES = 128 * 1024 * 1024


def handle_count() -> int | None:
    if os.name != "nt":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_current_process = kernel32.GetCurrentProcess
    get_current_process.restype = wintypes.HANDLE
    get_handle_count = kernel32.GetProcessHandleCount
    get_handle_count.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    get_handle_count.restype = wintypes.BOOL
    count = wintypes.DWORD()
    if not get_handle_count(get_current_process(), ctypes.byref(count)):
        return None
    return int(count.value)


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def result_digest(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256("\n".join(str(row["eventId"]) for row in rows).encode("utf-8")).hexdigest()


def run(*, iterations: int = 50, thread_count: int = 32, events_per_thread: int = 16) -> dict[str, Any]:
    if iterations < 1 or thread_count < 1 or events_per_thread < 1:
        raise ValueError("benchmark dimensions must be positive")
    with tempfile.TemporaryDirectory(prefix="codex-temporal-resource-") as temporary:
        root = Path(temporary)
        handoff = root / "handoff.ndjson"
        database = root / "temporal.sqlite3"
        expected = write_handoff(handoff, thread_count, events_per_thread)
        temporal_index.build_index(handoff, database, rebuild=True)
        start = "2026-01-01T00:00:00.000Z"
        end = "2026-02-01T00:00:00.000Z"
        expected_sorted = sorted(expected, key=lambda row: (str(row["timestampUtc"]), str(row["threadId"]), str(row["eventId"])))
        expected_count = len(expected_sorted)
        expected_digest = result_digest(expected_sorted)
        tracemalloc.start()
        gc.collect()
        before_current, _before_peak = tracemalloc.get_traced_memory()
        before_handles = handle_count()
        timings: list[float] = []
        query_ok = True
        for _ in range(iterations):
            started = time.perf_counter()
            rows = temporal_index.query_events(database, start, end)
            rows_by_thread = temporal_index.query_thread_events(database, ["synthetic-thread-00000"])
            timings.append((time.perf_counter() - started) * 1000)
            query_ok = query_ok and len(rows) == expected_count and result_digest(rows) == expected_digest and len(rows_by_thread) == events_per_thread
            rows = []
            rows_by_thread = []
        gc.collect()
        after_current, peak_bytes = tracemalloc.get_traced_memory()
        after_handles = handle_count()
        tracemalloc.stop()
        allocation_growth = max(0, after_current - before_current)
        handle_growth = None if before_handles is None or after_handles is None else after_handles - before_handles
        bounded_memory = allocation_growth <= 2 * 1024 * 1024 and peak_bytes <= PEAK_MEMORY_LIMIT_BYTES
        bounded_handles = handle_growth is None or handle_growth <= 2
        return {
            "contractVersion": CONTRACT,
            "status": "pass" if query_ok and bounded_memory and bounded_handles else "fail",
            "iterations": iterations,
            "threadCount": thread_count,
            "eventsPerThread": events_per_thread,
            "expectedEventCount": expected_count,
            "queryCorrect": query_ok,
            "queryP50Ms": round(percentile(timings, 0.50), 3),
            "queryP95Ms": round(percentile(timings, 0.95), 3),
            "pythonAllocationGrowthBytes": allocation_growth,
            "pythonPeakTracedBytes": int(peak_bytes),
            "handleCountBefore": before_handles,
            "handleCountAfter": after_handles,
            "handleGrowth": handle_growth,
            "boundedMemory": bounded_memory,
            "peakMemoryLimitBytes": PEAK_MEMORY_LIMIT_BYTES,
            "boundedHandles": bounded_handles,
        }


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--thread-count", type=int, default=32)
    parser.add_argument("--events-per-thread", type=int, default=16)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv or sys.argv[1:])
    try:
        result = run(iterations=args.iterations, thread_count=args.thread_count, events_per_thread=args.events_per_thread)
        atomic_json(args.out.resolve(), result)
        print(json.dumps({"status": result["status"], "out": str(args.out.resolve())}, separators=(",", ":")))
        return 0 if result["status"] == "pass" else 1
    except (OSError, ValueError, temporal_index.TemporalIndexError) as exc:
        print(json.dumps({"status": "error", "code": type(exc).__name__}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
