#!/usr/bin/env python3
"""Score match and no-match retrieval cases with uncertainty and holdout-safe output."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from thread_rag_benchmark_contract import (
    normalize_suite,
    percentile,
    read_json,
    suite_digests,
    verify_seal,
    wilson_interval,
)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def by_name(report: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    rows = report.get("results")
    if not isinstance(rows, list):
        raise ValueError(f"{label} report has no results array")
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = row.get("name")
        if not name or name in output:
            raise ValueError(f"{label} report contains a missing or duplicate case name")
        output[name] = row
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--seal", required=True, type=Path)
    parser.add_argument("--raw-report", required=True, type=Path)
    parser.add_argument("--hybrid-report", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--top1-threshold", type=float, default=0.975)
    parser.add_argument("--false-positive-threshold", type=float, default=0.05)
    parser.add_argument("--false-negative-threshold", type=float, default=0.05)
    args = parser.parse_args()

    suite = normalize_suite(read_json(args.suite.resolve()))
    seal = read_json(args.seal.resolve())
    mismatches = verify_seal(suite, seal)
    if mismatches:
        raise ValueError(f"Suite seal mismatch: {', '.join(mismatches)}")
    raw = by_name(read_json(args.raw_report.resolve()), "raw")
    hybrid = by_name(read_json(args.hybrid_report.resolve()), "hybrid")
    expected_names = {case["name"] for case in suite["cases"]}
    if set(raw) != expected_names or set(hybrid) != expected_names:
        raise ValueError("Reports must cover exactly the sealed suite case names")

    positive_count = candidate_hits = top1_hits = 0
    negative_count = false_positives = 0
    latencies: list[int | float] = []
    strata: dict[str, dict[str, int]] = {}
    details: list[dict[str, Any]] = []
    for case in suite["cases"]:
        raw_row = raw[case["name"]]
        hybrid_row = hybrid[case["name"]]
        if isinstance(raw_row.get("elapsedMs"), (int, float)):
            latencies.append(raw_row["elapsedMs"])
        predicted_ids = [item for item in hybrid_row.get("hybridThreadIds", []) if item]
        abstained = bool(hybrid_row.get("abstained")) or not predicted_ids
        bucket = strata.setdefault(case["stratum"], {"total": 0, "passed": 0})
        bucket["total"] += 1
        if case["expectation"] == "match":
            positive_count += 1
            expected = set(case["expectedThreadIds"])
            semantic_ids = [item for item in hybrid_row.get("semanticCandidateThreadIds", []) if item]
            candidate_hit = any(item in expected for item in semantic_ids)
            top1_hit = bool(predicted_ids and predicted_ids[0] in expected)
            candidate_hits += int(candidate_hit)
            top1_hits += int(top1_hit)
            passed = top1_hit
        else:
            negative_count += 1
            candidate_hit = None
            top1_hit = None
            false_positive = not abstained
            false_positives += int(false_positive)
            passed = not false_positive
        bucket["passed"] += int(passed)
        if suite["split"] != "holdout":
            details.append({
                "caseId": case["caseId"],
                "name": case["name"],
                "stratum": case["stratum"],
                "expectation": case["expectation"],
                "candidateHit": candidate_hit,
                "top1Hit": top1_hit,
                "abstained": abstained,
                "passed": passed,
            })

    false_negatives = positive_count - candidate_hits
    candidate = wilson_interval(candidate_hits, positive_count)
    top1 = wilson_interval(top1_hits, positive_count)
    fpr = wilson_interval(false_positives, negative_count)
    fnr = wilson_interval(false_negatives, positive_count)
    gates = {
        "candidateRecall100": candidate_hits == positive_count,
        "hybridTop1": bool(top1["rate"] is not None and top1["rate"] >= args.top1_threshold),
        "falsePositiveRate": negative_count == 0 or bool(fpr["rate"] is not None and fpr["rate"] <= args.false_positive_threshold),
        "falseNegativeRate": bool(fnr["rate"] is not None and fnr["rate"] <= args.false_negative_threshold),
    }
    report = {
        "suiteId": suite["suiteId"],
        "split": suite["split"],
        **suite_digests(suite),
        "caseDetailsSuppressed": suite["split"] == "holdout",
        "metrics": {
            "semanticCandidateRecall": candidate,
            "hybridTop1": top1,
            "falsePositiveRate": fpr,
            "falseNegativeRate": fnr,
            "latencyMs": {
                "count": len(latencies),
                "p50": percentile(latencies, 0.5),
                "p95": percentile(latencies, 0.95),
                "max": max(latencies) if latencies else None,
            },
            "strata": dict(sorted(strata.items())),
        },
        "thresholds": {
            "hybridTop1": args.top1_threshold,
            "falsePositiveRate": args.false_positive_threshold,
            "falseNegativeRate": args.false_negative_threshold,
        },
        "applicability": {
            "falsePositiveRate": negative_count > 0,
        },
        "gates": gates,
        "passed": all(gates.values()),
        "details": details,
    }
    atomic_json(args.out.resolve(), report)
    print(json.dumps({key: value for key, value in report.items() if key != "details"}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
