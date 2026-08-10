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
    parser.add_argument("--confirm-disposable-retrieval-notebook", action="store_true", help="Required acknowledgement because every case resets the notebook conversation")
    parser.add_argument("--allow-untracked-sources", action="store_true", help="Allow sources that are not linked by the projection state")
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between 0 and 1")
    if not args.confirm_disposable_retrieval_notebook:
        parser.error("--confirm-disposable-retrieval-notebook is required")
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


def normalize_cases(value: Any) -> list[dict[str, Any]]:
    cases = value.get("cases") if isinstance(value, dict) else value
    if not isinstance(cases, list) or not cases:
        raise ValueError("Cases must be a non-empty array or {cases:[...]} object")
    for index, case in enumerate(cases, 1):
        if not case.get("name") or not case.get("query") or not case.get("expectedThreadIds"):
            raise ValueError(f"Case {index} needs name, query, and expectedThreadIds")
        if isinstance(case["expectedThreadIds"], str):
            case["expectedThreadIds"] = [case["expectedThreadIds"]]
    return cases


async def reset_sacrificial_chat(client: NotebookLMClient, notebook_id: str) -> None:
    conversation_id = await client.chat.get_conversation_id(notebook_id)
    if conversation_id:
        await client.chat.delete_conversation(notebook_id, conversation_id)
    client.chat.clear_cache()


async def main() -> int:
    args = parse_args()
    state = read_json(args.state.resolve())
    source_to_thread = build_source_map(state)
    cases = normalize_cases(read_json(args.cases.resolve()))
    if args.limit is not None:
        cases = cases[: args.limit]
    output = args.out or args.state.resolve().parent / "runs" / f"retrieval-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{os.getpid()}.json"
    report: dict[str, Any] = {
        "startedAt": now_iso(),
        "profile": args.profile,
        "notebookId": args.notebook_id,
        "statePolicy": state.get("policyVersion"),
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
            await reset_sacrificial_chat(client, args.notebook_id)
            started = datetime.now(UTC)
            try:
                result = await client.chat.ask(args.notebook_id, case["query"])
                references = sorted(result.references, key=lambda item: item.citation_number)
                referenced_threads: list[str | None] = [source_to_thread.get(item.source_id) for item in references]
                expected = set(case["expectedThreadIds"])
                first_thread = referenced_threads[0] if referenced_threads else None
                actual_rank = next((rank for rank, thread_id in enumerate(referenced_threads, 1) if thread_id in expected), None)
                passed = first_thread in expected
                record = {
                    "name": case["name"],
                    "expectedThreadIds": sorted(expected),
                    "passedTop1": passed,
                    "actualRank": actual_rank,
                    "firstReferencedThreadId": first_thread,
                    "referencedThreadIds": referenced_threads,
                    "referenceCount": len(references),
                    "answerSha256": hashlib.sha256(result.answer.encode("utf-8")).hexdigest(),
                    "answerChars": len(result.answer),
                    "isFollowUp": result.is_follow_up,
                    "elapsedMs": int((datetime.now(UTC) - started).total_seconds() * 1000),
                }
            except Exception as error:
                record = {
                    "name": case["name"],
                    "expectedThreadIds": case["expectedThreadIds"],
                    "passedTop1": False,
                    "error": f"{type(error).__name__}: {error}",
                    "elapsedMs": int((datetime.now(UTC) - started).total_seconds() * 1000),
                }
            report["results"].append(record)
            atomic_json(output, report)
            print(
                f"[{index}/{len(cases)}] {'PASS' if record['passedTop1'] else 'FAIL'} "
                f"{case['name']} rank={record.get('actualRank')} {record['elapsedMs']}ms",
                flush=True,
            )
    passed = sum(1 for item in report["results"] if item["passedTop1"])
    total = len(report["results"])
    rate = passed / total if total else 0.0
    report["completedAt"] = now_iso()
    report["summary"] = {"passedTop1": passed, "failedTop1": total - passed, "total": total, "top1Recall": round(rate, 4), "thresholdPassed": rate >= args.threshold}
    atomic_json(output, report)
    print(json.dumps({"report": str(output), **report["summary"]}, indent=2))
    return 0 if rate >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
