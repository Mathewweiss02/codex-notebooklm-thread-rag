#!/usr/bin/env python3
"""Measure full-corpus local candidate recall without conflating it with final ranking."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


def expected_rank(results: list[dict[str, Any]], expected: set[str]) -> int | None:
    return next((index for index, item in enumerate(results, 1) if item.get("id") in expected), None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--node", default="node")
    parser.add_argument("--search-script", type=Path, default=Path(__file__).with_name("thread_search.mjs"))
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")

    state = read_json(args.state.resolve())
    suite = normalize_suite(read_json(args.cases.resolve()))
    projected_ids = sorted((state.get("threads") or {}).keys())
    if not projected_ids:
        raise ValueError("Projection state contains no tasks")
    report: dict[str, Any] = {
        "startedAt": now_iso(),
        "suiteId": suite["suiteId"],
        "split": suite["split"],
        **suite_digests(suite),
        "candidateLimit": args.limit,
        "projectedTaskCount": len(projected_ids),
        "results": [],
    }
    restriction = [part for thread_id in projected_ids for part in ("--thread", thread_id)]
    for index, case in enumerate(suite["cases"], 1):
        started = datetime.now(UTC)
        command = [
            args.node,
            str(args.search_script.resolve()),
            "--query",
            case["query"],
            "--limit",
            str(args.limit),
            "--min-score",
            "0",
            "--include-current",
            "--include-subagents",
            "--no-hydrate",
            "--json",
            *restriction,
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=240,
            check=False,
        )
        elapsed_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        if completed.returncode != 0:
            record = {
                "caseId": case["caseId"],
                "name": case["name"],
                "expectation": case["expectation"],
                "stratum": case["stratum"],
                "candidateHit": False,
                "error": (completed.stderr or completed.stdout or "local search failed").strip()[-1000:],
                "elapsedMs": elapsed_ms,
            }
        else:
            payload = json.loads(completed.stdout)
            results = payload.get("results") or []
            rank = expected_rank(results, set(case.get("expectedThreadIds") or []))
            record = {
                "caseId": case["caseId"],
                "name": case["name"],
                "expectation": case["expectation"],
                "stratum": case["stratum"],
                "expectedRank": rank,
                "candidateHit": rank is not None,
                "candidateThreadIds": [item.get("id") for item in results],
                "elapsedMs": elapsed_ms,
            }
        report["results"].append(record)
        atomic_json(args.out.resolve(), report)
        print(f"[{index}/{len(suite['cases'])}] {'HIT' if record['candidateHit'] else 'MISS'} {case['name']} rank={record.get('expectedRank')}", flush=True)

    positives = [item for item in report["results"] if item["expectation"] == "match"]
    hits = sum(1 for item in positives if item["candidateHit"])
    report["completedAt"] = now_iso()
    report["summary"] = {
        "candidateHits": hits,
        "positiveTotal": len(positives),
        "candidateRecall": round(hits / len(positives), 4) if positives else 0.0,
        "candidateWilson95": wilson_interval(hits, len(positives)),
        "errors": sum(1 for item in report["results"] if item.get("error")),
    }
    atomic_json(args.out.resolve(), report)
    print(json.dumps({"report": str(args.out.resolve()), **report["summary"]}, indent=2))
    return 0 if hits == len(positives) and report["summary"]["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
