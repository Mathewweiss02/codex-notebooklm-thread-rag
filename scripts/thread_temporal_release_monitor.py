#!/usr/bin/env python3
"""Evaluate retained runner reports for the wall-clock temporal soak gate."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


CONTRACT = "temporal-release-monitor-v1"
REQUIRED_STEPS = {"projection", "temporal-refresh", "sync", "retention"}


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def read_reports(runs_root: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    if not runs_root.is_dir():
        return reports
    for path in sorted(runs_root.glob("runner-*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            value["_path"] = path
            reports.append(value)
    return reports


def evaluate(
    reports: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    start_at: datetime | None = None,
    minimum_hours: float = 168.0,
    max_gap_hours: float = 2.0,
) -> dict[str, Any]:
    if minimum_hours <= 0 or max_gap_hours <= 0:
        raise ValueError("soak thresholds must be positive")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    usable: list[tuple[datetime, dict[str, Any]]] = []
    malformed = 0
    skipped_nonproduction = 0
    for report in reports:
        completed = parse_time(report.get("CompletedAt"))
        if completed is None:
            malformed += 1
            continue
        if start_at is not None and completed < start_at.astimezone(UTC):
            continue
        if report.get("DryRun") is True or report.get("ReconcileOnly") is True:
            skipped_nonproduction += 1
            continue
        usable.append((completed, report))
    usable.sort(key=lambda item: item[0])
    if not usable:
        return {
            "contractVersion": CONTRACT,
            "status": "open",
            "minimumHours": minimum_hours,
            "observedHours": 0.0,
            "eligibleRunCount": 0,
            "failedRunCount": 0,
            "malformedRunCount": malformed,
            "skippedNonproductionRunCount": skipped_nonproduction,
            "maxGapHours": None,
            "missingStepRunCount": 0,
        }
    first = usable[0][0]
    last = usable[-1][0]
    failed = 0
    missing_steps = 0
    gaps: list[float] = []
    for index, (completed, report) in enumerate(usable):
        if str(report.get("Status") or "").casefold() != "ok":
            failed += 1
        labels = {str(step.get("Label")) for step in report.get("Steps") or [] if isinstance(step, dict)}
        if not REQUIRED_STEPS.issubset(labels):
            missing_steps += 1
        if index:
            gaps.append((completed - usable[index - 1][0]).total_seconds() / 3600)
    observed_hours = max(0.0, (last - first).total_seconds() / 3600)
    max_gap = max(gaps) if gaps else 0.0
    sufficient_window = observed_hours >= minimum_hours
    clean = failed == 0 and malformed == 0 and missing_steps == 0 and max_gap <= max_gap_hours
    status = "pass" if sufficient_window and clean else ("fail" if not clean else "open")
    return {
        "contractVersion": CONTRACT,
        "status": status,
        "minimumHours": minimum_hours,
        "observedHours": round(observed_hours, 3),
        "observationStart": first.isoformat().replace("+00:00", "Z"),
        "observationEnd": last.isoformat().replace("+00:00", "Z"),
        "evaluatedAt": current.isoformat().replace("+00:00", "Z"),
        "eligibleRunCount": len(usable),
        "failedRunCount": failed,
        "malformedRunCount": malformed,
        "skippedNonproductionRunCount": skipped_nonproduction,
        "missingStepRunCount": missing_steps,
        "maxGapHours": round(max_gap, 3),
        "maxGapHoursAllowed": max_gap_hours,
        "requiredSteps": sorted(REQUIRED_STEPS),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--minimum-hours", type=float, default=168.0)
    parser.add_argument("--max-gap-hours", type=float, default=2.0)
    parser.add_argument("--start-at", help="ignore reports completed before this UTC timestamp")
    args = parser.parse_args(argv)
    try:
        start_at = parse_time(args.start_at) if args.start_at else None
        if args.start_at and start_at is None:
            raise ValueError("invalid --start-at timestamp")
        result = evaluate(
            read_reports(args.runs_root.resolve()),
            start_at=start_at,
            minimum_hours=args.minimum_hours,
            max_gap_hours=args.max_gap_hours,
        )
        write_json(args.out.resolve(), result)
        print(json.dumps({"status": result["status"], "eligibleRunCount": result["eligibleRunCount"], "observedHours": result["observedHours"], "out": str(args.out.resolve())}, separators=(",", ":")))
        return 0 if result["status"] == "pass" else 1
    except (OSError, ValueError):
        print(json.dumps({"status": "error", "code": "RELEASE_MONITOR_ERROR"}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
