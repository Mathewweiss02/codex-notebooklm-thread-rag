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
REQUIRED_RESOURCE_FIELDS = {
    "SampleCount",
    "Available",
    "WorkingSetPeakBytes",
    "PrivateBytesPeak",
    "HandleCountPeak",
    "ProcessorTimeDeltaMs",
}


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def read_reports(runs_root: Path, pattern: str = "runner-*.json") -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    if not runs_root.is_dir():
        return reports
    for path in sorted(runs_root.glob(pattern)):
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            value["_path"] = path
            reports.append(value)
    return reports


def has_resource_evidence(report: dict[str, Any]) -> bool:
    resource = report.get("Resource")
    if not isinstance(resource, dict) or not REQUIRED_RESOURCE_FIELDS.issubset(resource):
        return False
    try:
        return (
            resource["Available"] is True
            and int(resource["SampleCount"]) >= 2
            and int(resource["WorkingSetPeakBytes"]) >= 0
            and int(resource["PrivateBytesPeak"]) >= 0
            and int(resource["HandleCountPeak"]) >= 0
            and float(resource["ProcessorTimeDeltaMs"]) >= 0
        )
    except (TypeError, ValueError):
        return False


def evaluate(
    reports: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    start_at: datetime | None = None,
    minimum_hours: float = 168.0,
    max_gap_hours: float = 2.0,
    require_resource: bool = False,
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
            "missingResourceRunCount": 0,
            "resourceRequired": require_resource,
        }
    first = usable[0][0]
    last = usable[-1][0]
    failed = 0
    missing_steps = 0
    missing_resource = 0
    gaps: list[float] = []
    for index, (completed, report) in enumerate(usable):
        if str(report.get("Status") or "").casefold() != "ok":
            failed += 1
        labels = {str(step.get("Label")) for step in report.get("Steps") or [] if isinstance(step, dict)}
        if not REQUIRED_STEPS.issubset(labels):
            missing_steps += 1
        if require_resource and not has_resource_evidence(report):
            missing_resource += 1
        if index:
            gaps.append((completed - usable[index - 1][0]).total_seconds() / 3600)
    observed_hours = max(0.0, (last - first).total_seconds() / 3600)
    max_gap = max(gaps) if gaps else 0.0
    sufficient_window = observed_hours >= minimum_hours
    clean = (
        failed == 0
        and malformed == 0
        and missing_steps == 0
        and (not require_resource or missing_resource == 0)
        and max_gap <= max_gap_hours
    )
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
        "missingResourceRunCount": missing_resource,
        "resourceRequired": require_resource,
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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--runs-root", type=Path, help="disposable operational runner reports")
    source.add_argument("--evidence-root", type=Path, help="protected append-only aggregate soak evidence")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--minimum-hours", type=float, default=168.0)
    parser.add_argument("--max-gap-hours", type=float, default=2.0)
    parser.add_argument("--start-at", help="ignore reports completed before this UTC timestamp")
    parser.add_argument("--require-resource", action="store_true", help="require aggregate resource evidence in every eligible run")
    args = parser.parse_args(argv)
    try:
        start_at = parse_time(args.start_at) if args.start_at else None
        if args.start_at and start_at is None:
            raise ValueError("invalid --start-at timestamp")
        if args.evidence_root:
            source_root = args.evidence_root.resolve()
            reports = read_reports(source_root, "soak-*.json")
            source_kind = "protected-soak-evidence"
        else:
            source_root = args.runs_root.resolve()
            reports = read_reports(source_root)
            source_kind = "operational-run-reports"
        result = evaluate(
            reports,
            start_at=start_at,
            minimum_hours=args.minimum_hours,
            max_gap_hours=args.max_gap_hours,
            require_resource=args.require_resource,
        )
        result["sourceKind"] = source_kind
        write_json(args.out.resolve(), result)
        print(json.dumps({"status": result["status"], "eligibleRunCount": result["eligibleRunCount"], "observedHours": result["observedHours"], "out": str(args.out.resolve())}, separators=(",", ":")))
        return 0 if result["status"] == "pass" else 1
    except (OSError, ValueError):
        print(json.dumps({"status": "error", "code": "RELEASE_MONITOR_ERROR"}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
