#!/usr/bin/env python3
"""Benchmark NotebookLM task retrieval by mapping first citations back to Codex thread IDs."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from notebooklm import NotebookLMClient

from thread_rag_benchmark_contract import normalize_suite, suite_digests, wilson_interval


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--notebook-id", required=True)
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-semantic-attempts", type=int, default=2)
    parser.add_argument("--confirm-disposable-retrieval-notebook", action="store_true", help="Required acknowledgement because every case resets the notebook conversation")
    parser.add_argument("--allow-untracked-sources", action="store_true", help="Allow sources that are not linked by the projection state")
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between 0 and 1")
    if not args.confirm_disposable_retrieval_notebook:
        parser.error("--confirm-disposable-retrieval-notebook is required")
    if not 1 <= args.max_semantic_attempts <= 3:
        parser.error("--max-semantic-attempts must be between 1 and 3")
    return args


def build_source_map(state: dict[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for thread_id, thread in state.get("threads", {}).items():
        for part in thread.get("parts", []):
            source_id = part.get("sourceId")
            if not source_id:
                raise ValueError(f"Thread {thread_id} has an unuploaded part")
            owner = output.setdefault(source_id, thread_id)
            if owner != thread_id:
                raise ValueError("One live source id is assigned to multiple projected tasks")
    return output


async def reset_sacrificial_chat(client: NotebookLMClient, notebook_id: str) -> None:
    conversation_id = await client.chat.get_conversation_id(notebook_id)
    if conversation_id:
        await client.chat.delete_conversation(notebook_id, conversation_id)
    client.chat.clear_cache()


async def main() -> int:
    args = parse_args()
    state = read_json(args.state.resolve())
    source_to_thread = build_source_map(state)
    suite = normalize_suite(read_json(args.cases.resolve()))
    cases = suite["cases"]
    if args.limit is not None:
        cases = cases[: args.limit]
    output = args.out or args.state.resolve().parent / "runs" / f"retrieval-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{os.getpid()}.json"
    report: dict[str, Any] = {
        "startedAt": now_iso(),
        "profile": args.profile,
        "notebookId": args.notebook_id,
        "statePolicy": state.get("policyVersion"),
        "suiteId": suite["suiteId"],
        "split": suite["split"],
        **suite_digests(suite),
        "threshold": args.threshold,
        "caseCount": len(cases),
        "results": [],
    }
    async with NotebookLMClient.from_storage(profile=args.profile, chat_timeout=240.0) as client:
        live_ids = {source.id for source in await client.sources.list(args.notebook_id, strict=True)}
        missing = sorted(set(source_to_thread) - live_ids)
        if missing:
            raise ValueError(f"Live notebook is missing {len(missing)} state-linked sources")
        extra = sorted(live_ids - set(source_to_thread))
        if extra and not args.allow_untracked_sources:
            raise ValueError(f"Dedicated retrieval notebook contains {len(extra)} untracked sources")
        for index, case in enumerate(cases, 1):
            started = datetime.now(UTC)
            try:
                by_thread: dict[str, dict[str, Any]] = {}
                attempts: list[dict[str, Any]] = []
                for attempt in range(1, args.max_semantic_attempts + 1):
                    await reset_sacrificial_chat(client, args.notebook_id)
                    try:
                        result = await client.chat.ask(args.notebook_id, case["query"])
                    except Exception as error:
                        attempts.append({"attempt": attempt, "error": f"{type(error).__name__}: {error}"})
                        continue
                    references = sorted(result.references, key=lambda item: item.citation_number)
                    attempts.append({
                        "attempt": attempt,
                        "referenceCount": len(references),
                        "answerSha256": hashlib.sha256(result.answer.encode("utf-8")).hexdigest(),
                        "answerChars": len(result.answer),
                        "isFollowUp": result.is_follow_up,
                    })
                    for reference in references:
                        thread_id = source_to_thread.get(reference.source_id)
                        if not thread_id:
                            continue
                        candidate = by_thread.setdefault(thread_id, {
                            "threadId": thread_id,
                            "citationRank": reference.citation_number,
                            "firstAttempt": attempt,
                        })
                        candidate["citationRank"] = min(candidate["citationRank"], reference.citation_number)
                    if len(by_thread) >= 2:
                        break
                if not by_thread and any(item.get("error") for item in attempts):
                    raise RuntimeError("; ".join(item["error"] for item in attempts if item.get("error")))
                referenced_threads = [
                    item["threadId"]
                    for item in sorted(
                        by_thread.values(),
                        key=lambda item: (item["citationRank"], item["firstAttempt"], item["threadId"]),
                    )
                ]
                expected = set(case["expectedThreadIds"])
                first_thread = referenced_threads[0] if referenced_threads else None
                actual_rank = next((rank for rank, thread_id in enumerate(referenced_threads, 1) if thread_id in expected), None)
                abstained = first_thread is None
                passed_top1 = case["expectation"] == "match" and first_thread in expected
                passed_expectation = passed_top1 if case["expectation"] == "match" else abstained
                record = {
                    "caseId": case["caseId"],
                    "name": case["name"],
                    "expectation": case["expectation"],
                    "stratum": case["stratum"],
                    "expectedThreadIds": sorted(expected),
                    "passedTop1": passed_top1,
                    "passedExpectation": passed_expectation,
                    "abstained": abstained,
                    "actualRank": actual_rank,
                    "firstReferencedThreadId": first_thread,
                    "referencedThreadIds": referenced_threads,
                    "attempts": attempts,
                    "attemptsUsed": len(attempts),
                    "referenceCount": sum(int(item.get("referenceCount") or 0) for item in attempts),
                    "elapsedMs": int((datetime.now(UTC) - started).total_seconds() * 1000),
                }
            except Exception as error:
                record = {
                    "caseId": case["caseId"],
                    "name": case["name"],
                    "expectation": case["expectation"],
                    "stratum": case["stratum"],
                    "expectedThreadIds": case["expectedThreadIds"],
                    "passedTop1": False,
                    "passedExpectation": False,
                    "abstained": False,
                    "error": f"{type(error).__name__}: {error}",
                    "elapsedMs": int((datetime.now(UTC) - started).total_seconds() * 1000),
                }
            report["results"].append(record)
            atomic_json(output, report)
            print(
                f"[{index}/{len(cases)}] {'PASS' if record['passedExpectation'] else 'FAIL'} "
                f"{case['name']} rank={record.get('actualRank')} {record['elapsedMs']}ms",
                flush=True,
            )
    positives = [item for item in report["results"] if item["expectation"] == "match"]
    negatives = [item for item in report["results"] if item["expectation"] == "no_match"]
    passed = sum(1 for item in positives if item["passedTop1"])
    false_positives = sum(1 for item in negatives if not item["abstained"])
    rate = passed / len(positives) if positives else 0.0
    false_positive_rate = false_positives / len(negatives) if negatives else None
    report["completedAt"] = now_iso()
    report["summary"] = {
        "passedTop1": passed,
        "failedTop1": len(positives) - passed,
        "positiveTotal": len(positives),
        "negativeTotal": len(negatives),
        "top1Recall": round(rate, 4),
        "top1Wilson95": wilson_interval(passed, len(positives)),
        "falsePositives": false_positives,
        "falsePositiveRate": round(false_positive_rate, 4) if false_positive_rate is not None else None,
        "thresholdPassed": rate >= args.threshold,
    }
    atomic_json(output, report)
    print(json.dumps({"report": str(output), **report["summary"]}, indent=2))
    return 0 if rate >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
