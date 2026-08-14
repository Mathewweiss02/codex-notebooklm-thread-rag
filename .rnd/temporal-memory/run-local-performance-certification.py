#!/usr/bin/env python3
"""Run aggregate-only local temporal performance certification cases.

This harness measures the current derived temporal index without retaining
message text, identifiers, prompts, answers, or local source paths.  It keeps
the performance rows separate from synthetic scale and long-running soak
evidence so each certification claim has a current executable result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
CONTRACT = "temporal-local-performance-certification-v1"


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return round(ordered[index], 3)


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def aggregate_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs or any(run.get("status") != "ok" for run in runs):
        raise RuntimeError("one or more performance runs failed")
    durations = [float(run["durationMs"]) for run in runs]
    return {
        "runCount": len(runs),
        "passedCount": len(runs),
        "p50Ms": percentile(durations, 0.50),
        "p95Ms": percentile(durations, 0.95),
        "minMs": round(min(durations), 3),
        "maxMs": round(max(durations), 3),
        "coverage": runs[-1].get("coverage", {}),
        "resultDigest": digest([
            {key: value for key, value in run.items() if key != "durationMs"}
            for run in runs
        ]),
    }


def run_cli(
    python: str,
    node: str,
    database: Path,
    expression: str,
    timezone_name: str,
    now: str,
    mode: str,
    max_messages: int | None = None,
    max_chars: int | None = None,
) -> dict[str, Any]:
    command = [
        python,
        str(SCRIPTS / "thread_temporal_cli.py"),
        "--node",
        node,
        "context",
        "--db",
        str(database),
        "--expression",
        expression,
        "--timezone",
        timezone_name,
        "--now",
        now,
        "--mode",
        mode,
    ]
    if max_messages is not None:
        command.extend(["--max-messages", str(max_messages)])
    if max_chars is not None:
        command.extend(["--max-chars", str(max_chars)])
    started = time.perf_counter()
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
    duration_ms = (time.perf_counter() - started) * 1000
    if completed.returncode != 0:
        raise RuntimeError(f"temporal CLI failed with exit code {completed.returncode}")
    try:
        payload = json.loads(completed.stdout)
        result = payload["result"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError("temporal CLI returned malformed performance output") from exc
    if result.get("status") not in {"ok", "degraded", "empty"}:
        raise RuntimeError("temporal CLI returned an unsupported status")
    coverage = result.get("coverage", {})
    return {
        "status": "ok",
        "durationMs": duration_ms,
        "resultStatus": result.get("status"),
        "coverage": {
            "canonicalEventCount": int(coverage.get("canonicalEventCount", 0)),
            "includedEventCount": int(coverage.get("includedEventCount", 0)),
            "omittedEventCount": int(coverage.get("omittedEventCount", 0)),
            "segmentCount": int(coverage.get("segmentCount", 0)),
        },
    }


def run_cold_build_fixed(python: str, handoff: Path, repeats: int) -> dict[str, Any]:
    """Build isolated copies; kept separate so the command remains auditable."""
    runs: list[dict[str, Any]] = []
    for _ in range(repeats):
        with tempfile.TemporaryDirectory(prefix="temporal-perf-") as temporary:
            database = Path(temporary) / "temporal.sqlite3"
            started = time.perf_counter()
            completed = subprocess.run(
                [
                    python,
                    "-c",
                    "from pathlib import Path; import json, sys; from thread_temporal_index import build_index; print(json.dumps(build_index(Path(sys.argv[1]), Path(sys.argv[2]), rebuild=True)))",
                    str(handoff),
                    str(database),
                ],
                cwd=str(SCRIPTS),
                env={**os.environ, "PYTHONPATH": str(SCRIPTS)},
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"cold index build failed with exit code {completed.returncode}")
            duration_ms = (time.perf_counter() - started) * 1000
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError("cold index build returned malformed output") from exc
            runs.append({
                "status": "ok",
                "durationMs": duration_ms,
                "coverage": {
                    "eventCount": int(payload.get("eventCount", 0)),
                    "quarantineCount": int(payload.get("quarantineCount", 0)),
                },
            })
    return aggregate_runs(runs)


def run_warm_case(
    node: str,
    database: Path,
    expression: str,
    timezone_name: str,
    now: str,
    mode: str,
    repeats: int,
) -> dict[str, Any]:
    """Measure repeated context selection in one process over a warm DB."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    from thread_temporal_cli import local_context, parse_args, resolve_period  # noqa: PLC0415

    args = parse_args([
        "--node", node, "context", "--db", str(database), "--expression", expression,
        "--timezone", timezone_name, "--now", now, "--mode", mode,
    ])
    period = resolve_period(args)
    runs: list[dict[str, Any]] = []
    for _ in range(repeats):
        started = time.perf_counter()
        result = local_context(args, period)
        duration_ms = (time.perf_counter() - started) * 1000
        coverage = result.get("coverage", {})
        runs.append({
            "status": "ok",
            "durationMs": duration_ms,
            "resultStatus": result.get("status"),
            "coverage": {
                "canonicalEventCount": int(coverage.get("canonicalEventCount", 0)),
                "includedEventCount": int(coverage.get("includedEventCount", 0)),
                "omittedEventCount": int(coverage.get("omittedEventCount", 0)),
                "segmentCount": int(coverage.get("segmentCount", 0)),
            },
        })
    return aggregate_runs(runs)


def run_case(
    python: str,
    node: str,
    database: Path,
    expression: str,
    timezone_name: str,
    now: str,
    mode: str,
    repeats: int,
    max_messages: int | None = None,
    max_chars: int | None = None,
) -> dict[str, Any]:
    runs = [
        run_cli(python, node, database, expression, timezone_name, now, mode, max_messages, max_chars)
        for _ in range(repeats)
    ]
    return aggregate_runs(runs)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--node", default=shutil.which("node") or "node")
    parser.add_argument("--timezone", default="America/New_York")
    parser.add_argument("--now", default="2026-08-14T12:00:00.000Z")
    parser.add_argument("--repeats", type=int, default=5)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.repeats < 3:
        raise SystemExit("--repeats must be at least 3")
    database = args.db.resolve()
    handoff = args.handoff.resolve()
    if not database.is_file() or not handoff.is_file():
        raise SystemExit("database and handoff must exist")

    cold_build = run_cold_build_fixed(args.python, handoff, args.repeats)
    warm_day = run_warm_case(args.node, database, "today", args.timezone, args.now, "standard", args.repeats)
    cold_day = run_case(args.python, args.node, database, "today", args.timezone, args.now, "standard", args.repeats)
    week = run_case(
        args.python,
        args.node,
        database,
        "week to date",
        args.timezone,
        args.now,
        "deep",
        args.repeats,
        max_messages=10_000,
        max_chars=2_000_000,
    )

    thresholds = {
        "warmDayP95Ms": 500,
        "coldDayP95Ms": 2_000,
        "weekContextP95Ms": 3_000,
        "weekMustBeComplete": True,
    }
    week_complete = week["coverage"].get("omittedEventCount", 0) == 0
    cases = {
        "PERF-001": {"status": "pass", "measurement": cold_build},
        "PERF-004": {"status": "pass" if warm_day["p95Ms"] <= thresholds["warmDayP95Ms"] else "fail", "measurement": warm_day},
        "PERF-005": {"status": "pass" if cold_day["p95Ms"] <= thresholds["coldDayP95Ms"] else "fail", "measurement": cold_day},
        "PERF-006": {"status": "pass" if week["p95Ms"] <= thresholds["weekContextP95Ms"] and week_complete else "fail", "measurement": week},
    }
    payload = {
        "contractVersion": CONTRACT,
        "status": "pass" if all(case["status"] == "pass" for case in cases.values()) else "fail",
        "generatedAtUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime": {"python": "pinned-runtime", "node": "node", "timezone": args.timezone, "nowUtc": args.now},
        "corpus": {
            "eventCount": int(cold_build["coverage"].get("eventCount", 0)),
            "quarantineCount": int(cold_build["coverage"].get("quarantineCount", 0)),
        },
        "thresholds": thresholds,
        "cases": cases,
        "evidencePolicy": "aggregate-only; no message text, identifiers, prompts, answers, or local source paths",
    }
    payload["resultDigest"] = digest(payload)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "caseCount": len(cases), "resultDigest": payload["resultDigest"], "out": str(args.out.resolve())}))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
