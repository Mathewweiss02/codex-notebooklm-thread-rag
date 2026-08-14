"""Independent TM-006 activity-segmentation experiment.

This is an R&D harness, not production code.  The expected activity labels are
the oracle; the candidate segmenter deliberately has no dependency on the
future production implementation so threshold selection cannot pass by
sharing a bug with it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include an offset: {value}")
    return parsed.astimezone(timezone.utc)


def fixture() -> list[dict[str, str]]:
    """Return the frozen labeled cases used only by this experiment."""

    return [
        # Cross-midnight continuation; 70 minutes starts a new activity.
        {"eventId": "alpha-01", "threadId": "thread-alpha", "timestampUtc": "2026-02-01T23:55:00Z", "activityId": "alpha-1"},
        {"eventId": "alpha-02", "threadId": "thread-alpha", "timestampUtc": "2026-02-02T00:05:00Z", "activityId": "alpha-1"},
        {"eventId": "alpha-03", "threadId": "thread-alpha", "timestampUtc": "2026-02-02T00:20:00Z", "activityId": "alpha-1"},
        {"eventId": "alpha-04", "threadId": "thread-alpha", "timestampUtc": "2026-02-02T01:30:00Z", "activityId": "alpha-2"},
        {"eventId": "alpha-05", "threadId": "thread-alpha", "timestampUtc": "2026-02-02T01:45:00Z", "activityId": "alpha-2"},
        # A 45-minute continuation defeats an over-aggressive 15/30-minute cut.
        {"eventId": "beta-01", "threadId": "thread-beta", "timestampUtc": "2026-02-03T09:00:00Z", "activityId": "beta-1"},
        {"eventId": "beta-02", "threadId": "thread-beta", "timestampUtc": "2026-02-03T09:45:00Z", "activityId": "beta-1"},
        {"eventId": "beta-03", "threadId": "thread-beta", "timestampUtc": "2026-02-03T10:00:00Z", "activityId": "beta-1"},
        {"eventId": "beta-04", "threadId": "thread-beta", "timestampUtc": "2026-02-03T11:15:00Z", "activityId": "beta-2"},
        {"eventId": "beta-05", "threadId": "thread-beta", "timestampUtc": "2026-02-03T11:30:00Z", "activityId": "beta-2"},
        # A 130-minute gap remains a split even for the largest candidate.
        {"eventId": "gamma-01", "threadId": "thread-gamma", "timestampUtc": "2026-02-04T13:00:00Z", "activityId": "gamma-1"},
        {"eventId": "gamma-02", "threadId": "thread-gamma", "timestampUtc": "2026-02-04T13:20:00Z", "activityId": "gamma-1"},
        {"eventId": "gamma-03", "threadId": "thread-gamma", "timestampUtc": "2026-02-04T15:30:00Z", "activityId": "gamma-2"},
        # Exactly 60 minutes remains joined; 61 minutes starts a new segment.
        {"eventId": "delta-01", "threadId": "thread-delta", "timestampUtc": "2026-02-05T18:00:00Z", "activityId": "delta-1"},
        {"eventId": "delta-02", "threadId": "thread-delta", "timestampUtc": "2026-02-05T19:00:00Z", "activityId": "delta-1"},
        {"eventId": "delta-03", "threadId": "thread-delta", "timestampUtc": "2026-02-05T20:01:00Z", "activityId": "delta-2"},
        {"eventId": "delta-04", "threadId": "thread-delta", "timestampUtc": "2026-02-05T20:10:00Z", "activityId": "delta-2"},
    ]


def segment(records: list[dict[str, str]], threshold_minutes: int) -> dict[str, str]:
    """Segment each thread in timestamp order; a gap strictly greater than
    the threshold begins a new activity.  The strict boundary is intentional
    and is itself asserted by the fixture.
    """

    assigned: dict[str, str] = {}
    by_thread: dict[str, list[dict[str, str]]] = {}
    for record in records:
        by_thread.setdefault(record["threadId"], []).append(record)

    for thread_id, thread_records in by_thread.items():
        ordered = sorted(thread_records, key=lambda item: (parse_utc(item["timestampUtc"]), item["eventId"]))
        previous: datetime | None = None
        segment_number = 0
        for record in ordered:
            current = parse_utc(record["timestampUtc"])
            if previous is None or (current - previous).total_seconds() > threshold_minutes * 60:
                segment_number += 1
            assigned[record["eventId"]] = f"{thread_id}#segment-{segment_number}"
            previous = current
    return assigned


def pairwise_metrics(records: list[dict[str, str]], assigned: dict[str, str]) -> dict[str, Any]:
    expected_by_id = {record["eventId"]: record["activityId"] for record in records}
    ids = sorted(expected_by_id)
    true_positive = false_positive = false_negative = true_negative = 0
    for index, left in enumerate(ids):
        for right in ids[index + 1 :]:
            # Activities from different threads are never allowed to merge.
            expected_same = (
                expected_by_id[left] == expected_by_id[right]
                and next(record["threadId"] for record in records if record["eventId"] == left)
                == next(record["threadId"] for record in records if record["eventId"] == right)
            )
            predicted_same = assigned[left] == assigned[right]
            if expected_same and predicted_same:
                true_positive += 1
            elif not expected_same and predicted_same:
                false_positive += 1
            elif expected_same:
                false_negative += 1
            else:
                true_negative += 1

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    predicted_segments = len(set(assigned.values()))
    expected_segments = len({(record["threadId"], record["activityId"]) for record in records})
    return {
        "truePositivePairs": true_positive,
        "falsePositivePairs": false_positive,
        "falseNegativePairs": false_negative,
        "trueNegativePairs": true_negative,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "predictedSegments": predicted_segments,
        "expectedSegments": expected_segments,
        "exactOraclePartition": (
            false_positive == 0
            and false_negative == 0
            and predicted_segments == expected_segments
        ),
    }


def run(thresholds: list[int]) -> dict[str, Any]:
    records = fixture()
    results: list[dict[str, Any]] = []
    for threshold in thresholds:
        assigned = segment(records, threshold)
        metrics = pairwise_metrics(records, assigned)
        results.append({"thresholdMinutes": threshold, **metrics})

    exact = [result for result in results if result["exactOraclePartition"]]
    if not exact:
        raise RuntimeError("no candidate threshold matched the frozen activity oracle")
    selected = min(exact, key=lambda result: result["thresholdMinutes"])
    canonical = {
        "experiment": "TM-006",
        "contract": "activity-segmentation-experiment-v1",
        "fixtureEventCount": len(records),
        "expectedActivityCount": len({(record["threadId"], record["activityId"]) for record in records}),
        "thresholds": results,
        "selectedPolicy": {
            "thresholdMinutes": selected["thresholdMinutes"],
            "newSegmentWhen": "timestamp gap > threshold",
            "threadBoundary": "always-new activity domain",
            "crossMidnight": "does not split by local date",
            "tieBreak": ["timestampUtc", "eventId"],
        },
        "oracleNotes": [
            "expected activity labels are independent of the candidate segmenter",
            "pairwise precision and recall count merges and fragments separately",
            "this is a synthetic policy-selection experiment, not a production-corpus quality claim",
        ],
    }
    digest_input = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    canonical["resultDigest"] = hashlib.sha256(digest_input).hexdigest()
    return canonical


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--threshold", type=int, action="append", dest="thresholds")
    args = parser.parse_args()
    thresholds = args.thresholds or [15, 30, 60, 120]
    if any(threshold <= 0 for threshold in thresholds):
        parser.error("thresholds must be positive minutes")
    result = run(thresholds)
    payload = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.out.with_name(f".{args.out.name}.tmp")
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(args.out)
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
