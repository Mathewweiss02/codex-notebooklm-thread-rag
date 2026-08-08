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


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-report", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--state", type=Path, help="Projection state used to recover authoritative task titles")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--node")
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between 0 and 1")

    raw = read_json(args.raw_report.resolve())
    state_path = args.state.resolve() if args.state else args.raw_report.resolve().parent.parent / "state.json"
    state = read_json(state_path) if state_path.is_file() else {"threads": {}}
    cases_value = read_json(args.cases.resolve())
    cases = cases_value.get("cases") if isinstance(cases_value, dict) else cases_value
    by_name = {case["name"]: case for case in cases}
    report: dict[str, Any] = {
        "startedAt": now_iso(),
        "rawReport": str(args.raw_report.resolve()),
        "threshold": args.threshold,
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
        semantic = [
            {
                "threadId": thread_id,
                "title": (state.get("threads", {}).get(thread_id) or {}).get("title"),
                "citationRank": rank,
                "score": round(1 / rank, 6),
                "device": "recorded-benchmark",
            }
            for rank, thread_id in enumerate(thread_ids, 1)
        ]
        started = datetime.now(UTC)
        try:
            ranked, verification = local_rerank_candidates(case["query"], semantic, node_path=args.node)
            final_ids = [item["threadId"] for item in ranked if item.get("locallyVerified")]
            expected = set(case["expectedThreadIds"] if isinstance(case["expectedThreadIds"], list) else [case["expectedThreadIds"]])
            final_rank = next((rank for rank, thread_id in enumerate(final_ids, 1) if thread_id in expected), None)
            record = {
                "name": case["name"],
                "expectedThreadIds": sorted(expected),
                "semanticCandidateThreadIds": thread_ids,
                "semanticExpectedRank": raw_result.get("actualRank"),
                "semanticPassedTop1": raw_result.get("passedTop1") is True,
                "hybridThreadIds": final_ids,
                "hybridExpectedRank": final_rank,
                "passedHybridTop1": bool(final_ids and final_ids[0] in expected),
                "localVerification": verification,
            }
        except Exception as error:
            record = {
                "name": case["name"],
                "semanticCandidateThreadIds": thread_ids,
                "semanticPassedTop1": raw_result.get("passedTop1") is True,
                "passedHybridTop1": False,
                "error": f"{type(error).__name__}: {error}",
            }
        record["elapsedMs"] = int((datetime.now(UTC) - started).total_seconds() * 1000)
        report["results"].append(record)
        atomic_json(args.out.resolve(), report)
        print(f"[{index}/{len(raw.get('results') or [])}] {'PASS' if record['passedHybridTop1'] else 'FAIL'} {case['name']} rank={record.get('hybridExpectedRank')}", flush=True)

    total = len(report["results"])
    semantic_top1 = sum(1 for item in report["results"] if item.get("semanticPassedTop1"))
    candidate_hits = sum(1 for item in report["results"] if item.get("semanticExpectedRank") is not None)
    hybrid_top1 = sum(1 for item in report["results"] if item.get("passedHybridTop1"))
    hybrid_rate = hybrid_top1 / total if total else 0
    report["completedAt"] = now_iso()
    threshold_passed = candidate_hits == total and hybrid_rate >= args.threshold
    report["summary"] = {
        "total": total,
        "semanticTop1": semantic_top1,
        "semanticTop1Recall": round(semantic_top1 / total, 4) if total else 0,
        "semanticCandidateHits": candidate_hits,
        "semanticCandidateRecall": round(candidate_hits / total, 4) if total else 0,
        "hybridTop1": hybrid_top1,
        "hybridTop1Recall": round(hybrid_rate, 4),
        "thresholdPassed": threshold_passed,
    }
    atomic_json(args.out.resolve(), report)
    print(json.dumps({"report": str(args.out.resolve()), **report["summary"]}, indent=2))
    return 0 if threshold_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
