#!/usr/bin/env python3
"""Rerank a recorded NotebookLM retrieval run against authoritative local Codex history."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from notebooklm_thread_search import local_rerank_candidates
from thread_rag_benchmark_contract import normalize_suite, suite_digests, wilson_interval


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def normalized_expected_ids(case: dict[str, Any]) -> set[str]:
    value = case.get("expectedThreadIds", [])
    return set(value if isinstance(value, list) else [value])


def first_expected_rank(thread_ids: list[str], expected: set[str]) -> int | None:
    return next((rank for rank, thread_id in enumerate(thread_ids, 1) if thread_id in expected), None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-report", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--state", type=Path, help="Projection state used to recover authoritative task titles")
    parser.add_argument("--local-candidate-report", type=Path, help="Optional independent full-corpus candidate report to union with NotebookLM citations")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--node")
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between 0 and 1")

    raw = read_json(args.raw_report.resolve())
    state_path = args.state.resolve() if args.state else args.raw_report.resolve().parent.parent / "state.json"
    state = read_json(state_path) if state_path.is_file() else {"threads": {}}
    suite = normalize_suite(read_json(args.cases.resolve()))
    cases = suite["cases"]
    by_name = {case["name"]: case for case in cases}
    local_by_name: dict[str, dict[str, Any]] = {}
    if args.local_candidate_report:
        local_report = read_json(args.local_candidate_report.resolve())
        if local_report.get("suiteSha256") != suite_digests(suite)["suiteSha256"]:
            raise ValueError("Local candidate report does not match the benchmark suite")
        local_by_name = {item["name"]: item for item in local_report.get("results") or []}
    report: dict[str, Any] = {
        "startedAt": now_iso(),
        "rawReport": str(args.raw_report.resolve()),
        "threshold": args.threshold,
        "suiteId": suite["suiteId"],
        "split": suite["split"],
        **suite_digests(suite),
        "results": [],
    }
    for index, raw_result in enumerate(raw.get("results") or [], 1):
        case = by_name.get(raw_result.get("name"))
        if case is None:
            raise ValueError(f"No benchmark case matches {raw_result.get('name')}")
        thread_ids: list[str] = []
        for thread_id in raw_result.get("referencedThreadIds") or []:
            if thread_id and thread_id not in thread_ids:
                thread_ids.append(thread_id)
        combined_thread_ids = list(thread_ids)
        local_record = local_by_name.get(case["name"], {})
        for thread_id in local_record.get("candidateThreadIds") or []:
            if thread_id and thread_id not in combined_thread_ids:
                combined_thread_ids.append(thread_id)
        semantic = [
            {
                "threadId": thread_id,
                "title": (state.get("threads", {}).get(thread_id) or {}).get("title"),
                "citationRank": rank,
                "score": round(1 / rank, 6),
                "device": "recorded-benchmark",
            }
            for rank, thread_id in enumerate(combined_thread_ids, 1)
        ]
        started = datetime.now(UTC)
        try:
            ranked, verification = local_rerank_candidates(case["query"], semantic, node_path=args.node)
            diagnostic_ids = [item["threadId"] for item in ranked]
            abstained = bool(verification.get("abstained"))
            final_ids = [] if abstained else diagnostic_ids
            expected = normalized_expected_ids(case)
            semantic_rank = first_expected_rank(thread_ids, expected)
            final_rank = first_expected_rank(final_ids, expected)
            passed_top1 = case["expectation"] == "match" and bool(final_ids and final_ids[0] in expected)
            passed_expectation = passed_top1 if case["expectation"] == "match" else abstained
            record = {
                "caseId": case["caseId"],
                "name": case["name"],
                "expectation": case["expectation"],
                "stratum": case["stratum"],
                "expectedThreadIds": sorted(expected),
                "semanticCandidateThreadIds": thread_ids,
                "combinedCandidateThreadIds": combined_thread_ids,
                "semanticExpectedRank": semantic_rank,
                "combinedExpectedRank": first_expected_rank(combined_thread_ids, expected),
                "semanticPassedTop1": semantic_rank == 1,
                "hybridThreadIds": final_ids,
                "diagnosticThreadIds": diagnostic_ids,
                "hybridCandidates": [
                    {
                        "threadId": item["threadId"],
                        "semanticRank": item.get("semanticRank"),
                        "localRank": item.get("localRank"),
                        "localScore": item.get("localScore"),
                        "localCoverage": item.get("localCoverage"),
                        "locallyVerified": item.get("locallyVerified"),
                        "titleQueryOverlap": item.get("titleQueryOverlap"),
                        "compoundTitleQueryOverlap": item.get("compoundTitleQueryOverlap"),
                        "duplicateTitleCount": item.get("duplicateTitleCount"),
                        "duplicateGroupQueryOverlap": item.get("duplicateGroupQueryOverlap"),
                        "duplicateGroupCompetingTitleOverlap": item.get("duplicateGroupCompetingTitleOverlap"),
                        "duplicateGroupBlockedByCompetingEvidence": item.get("duplicateGroupBlockedByCompetingEvidence"),
                        "exactTitleMatch": item.get("exactTitleMatch"),
                        "hybridScore": item.get("hybridScore"),
                        "finalRank": item.get("finalRank"),
                    }
                    for item in ranked
                ],
                "hybridExpectedRank": final_rank,
                "passedHybridTop1": passed_top1,
                "passedExpectation": passed_expectation,
                "abstained": abstained,
                "localVerification": verification,
            }
        except Exception as error:
            record = {
                "caseId": case["caseId"],
                "name": case["name"],
                "expectation": case["expectation"],
                "stratum": case["stratum"],
                "semanticCandidateThreadIds": thread_ids,
                "combinedCandidateThreadIds": combined_thread_ids,
                "semanticExpectedRank": first_expected_rank(thread_ids, normalized_expected_ids(case)),
                "combinedExpectedRank": first_expected_rank(combined_thread_ids, normalized_expected_ids(case)),
                "semanticPassedTop1": first_expected_rank(thread_ids, normalized_expected_ids(case)) == 1,
                "passedHybridTop1": False,
                "passedExpectation": False,
                "abstained": False,
                "error": f"{type(error).__name__}: {error}",
            }
        record["elapsedMs"] = int((datetime.now(UTC) - started).total_seconds() * 1000)
        report["results"].append(record)
        atomic_json(args.out.resolve(), report)
        print(f"[{index}/{len(raw.get('results') or [])}] {'PASS' if record['passedExpectation'] else 'FAIL'} {case['name']} rank={record.get('hybridExpectedRank')}", flush=True)

    total = len(report["results"])
    positives = [item for item in report["results"] if item.get("expectation") == "match"]
    negatives = [item for item in report["results"] if item.get("expectation") == "no_match"]
    semantic_top1 = sum(1 for item in positives if item.get("semanticPassedTop1"))
    candidate_hits = sum(1 for item in positives if item.get("semanticExpectedRank") is not None)
    combined_candidate_hits = sum(1 for item in positives if item.get("combinedExpectedRank") is not None)
    hybrid_top1 = sum(1 for item in positives if item.get("passedHybridTop1"))
    false_positives = sum(1 for item in negatives if not item.get("abstained"))
    hybrid_rate = hybrid_top1 / len(positives) if positives else 0
    report["completedAt"] = now_iso()
    threshold_passed = combined_candidate_hits == len(positives) and hybrid_rate >= args.threshold
    report["summary"] = {
        "total": total,
        "positiveTotal": len(positives),
        "negativeTotal": len(negatives),
        "semanticTop1": semantic_top1,
        "semanticTop1Recall": round(semantic_top1 / len(positives), 4) if positives else 0,
        "semanticCandidateHits": candidate_hits,
        "semanticCandidateRecall": round(candidate_hits / len(positives), 4) if positives else 0,
        "semanticCandidateWilson95": wilson_interval(candidate_hits, len(positives)),
        "combinedCandidateHits": combined_candidate_hits,
        "combinedCandidateRecall": round(combined_candidate_hits / len(positives), 4) if positives else 0,
        "combinedCandidateWilson95": wilson_interval(combined_candidate_hits, len(positives)),
        "hybridTop1": hybrid_top1,
        "hybridTop1Recall": round(hybrid_rate, 4),
        "hybridTop1Wilson95": wilson_interval(hybrid_top1, len(positives)),
        "falsePositives": false_positives,
        "falsePositiveRate": round(false_positives / len(negatives), 4) if negatives else None,
        "thresholdPassed": threshold_passed,
    }
    atomic_json(args.out.resolve(), report)
    print(json.dumps({"report": str(args.out.resolve()), **report["summary"]}, indent=2))
    return 0 if threshold_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
