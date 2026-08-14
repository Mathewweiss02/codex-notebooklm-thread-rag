#!/usr/bin/env python3
"""Measure packed multi-question NotebookLM retrieval without storing answer text."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from notebooklm import NotebookLMClient

from notebooklm_thread_search import local_rerank_candidates
from redaction_contract import sanitize_remote_text
from thread_rag_benchmark_contract import normalize_suite, suite_digests


HEADING_RE = re.compile(r"(?im)^\s*#{1,6}\s*Q(\d+)\b[^\r\n]*$")


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(temporary, path)


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * (position - lower))


def build_source_map(state: dict[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for thread_id, thread in state.get("threads", {}).items():
        parts = thread.get("parts", [])
        # Auto-enrollment can checkpoint a newly visible task before its live
        # source upload finishes.  It is not part of the current remote corpus
        # until every current part has a source ID; skip the incomplete task
        # and let the report disclose the coverage gap.
        if not parts or any(not part.get("sourceId") for part in parts):
            continue
        for part in parts:
            source_id = part.get("sourceId")
            owner = output.setdefault(source_id, thread_id)
            if owner != thread_id:
                raise ValueError("one live source id is assigned to multiple projected tasks")
    return output


def build_packed_prompt(cases: list[dict[str, Any]]) -> tuple[str, int]:
    lines = [
        "Treat each numbered question below as independent retrieval.",
        "Return one section per question headed exactly ## Q1, ## Q2, and so on.",
        "Inside each section, identify the best matching Codex task or say NO MATCH.",
        "Place source citations inside the section they support. Do not combine questions.",
        "",
    ]
    redactions = 0
    for index, case in enumerate(cases, 1):
        safe_query, counts = sanitize_remote_text(case["query"])
        redactions += sum(counts.values())
        lines.extend((f"Q{index}: {safe_query}", ""))
    return "\n".join(lines).strip(), redactions


def answer_sections(answer: str, count: int) -> dict[int, tuple[int, int]]:
    markers: list[tuple[int, int]] = []
    seen: set[int] = set()
    for match in HEADING_RE.finditer(answer):
        number = int(match.group(1))
        if 1 <= number <= count and number not in seen:
            markers.append((number, match.start()))
            seen.add(number)
    markers.sort(key=lambda item: item[1])
    return {
        number: (start, markers[index + 1][1] if index + 1 < len(markers) else len(answer))
        for index, (number, start) in enumerate(markers)
    }


def map_references_to_sections(
    answer: str,
    references: list[Any],
    section_count: int,
) -> tuple[dict[int, list[Any]], int]:
    spans = answer_sections(answer, section_count)
    mapped: dict[int, list[Any]] = {index: [] for index in range(1, section_count + 1)}
    unmapped = 0
    for reference in references:
        citation_number = getattr(reference, "citation_number", None)
        markers = (
            f"[{citation_number}]",
            f"【{citation_number}】",
        ) if citation_number is not None else ()
        marker_positions = [answer.find(marker) for marker in markers]
        position = min((value for value in marker_positions if value >= 0), default=-1)
        if position < 0:
            position = getattr(reference, "answer_start_char", None)
        if position is None or position < 0:
            unmapped += 1
            continue
        section = next(
            (number for number, (start, end) in spans.items() if start <= position < end),
            None,
        )
        if section is None:
            unmapped += 1
        else:
            mapped[section].append(reference)
    return mapped, unmapped


def unique_threads(references: list[Any], source_to_thread: dict[str, str]) -> list[str]:
    ordered = sorted(
        references,
        key=lambda item: (
            getattr(item, "citation_number", None) is None,
            getattr(item, "citation_number", None) or 1_000_000,
        ),
    )
    output: list[str] = []
    for reference in ordered:
        thread_id = source_to_thread.get(getattr(reference, "source_id", ""))
        if thread_id and thread_id not in output:
            output.append(thread_id)
    return output


async def reset_sacrificial_chat(client: NotebookLMClient, notebook_id: str) -> None:
    conversation_id = await client.chat.get_conversation_id(notebook_id)
    if conversation_id:
        await client.chat.delete_conversation(notebook_id, conversation_id)
    client.chat.clear_cache()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--notebook-id", required=True)
    parser.add_argument("--pack-sizes", nargs="+", type=int, default=[2, 4])
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--match-only", action="store_true")
    parser.add_argument("--node", help="Node.js executable used for local candidate reranking")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--confirm-disposable-retrieval-notebook", action="store_true")
    args = parser.parse_args()
    if not args.confirm_disposable_retrieval_notebook:
        parser.error("--confirm-disposable-retrieval-notebook is required")
    if args.limit < 1:
        parser.error("--limit must be positive")
    if any(size < 1 or size > 8 for size in args.pack_sizes):
        parser.error("--pack-sizes values must be between 1 and 8")
    return args


async def main() -> int:
    args = parse_args()
    state = read_json(args.state.resolve())
    source_to_thread = build_source_map(state)
    suite = normalize_suite(read_json(args.cases.resolve()))
    cases = suite["cases"]
    if args.match_only:
        cases = [case for case in cases if case["expectation"] == "match"]
    cases = cases[: args.limit]
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "startedAt": now_iso(),
        "suiteId": suite["suiteId"],
        "split": suite["split"],
        **suite_digests(suite),
        "caseCount": len(cases),
        "packSizes": sorted(set(args.pack_sizes)),
        "results": [],
    }
    report["sourceCoverage"] = {
        "stateThreadCount": len(state.get("threads") or {}),
        "mappedThreadCount": len(set(source_to_thread.values())),
        "mappedSourceCount": len(source_to_thread),
        "incompleteThreadCount": sum(
            1
            for thread in (state.get("threads") or {}).values()
            if not thread.get("parts") or any(not part.get("sourceId") for part in thread.get("parts", []))
        ),
    }
    async with NotebookLMClient.from_storage(profile=args.profile, chat_timeout=240.0) as client:
        live_ids = {source.id for source in await client.sources.list(args.notebook_id, strict=True)}
        if missing := sorted(set(source_to_thread) - live_ids):
            raise ValueError(f"Live notebook is missing {len(missing)} state-linked sources")
        if extra := sorted(live_ids - set(source_to_thread)):
            raise ValueError(f"Dedicated retrieval notebook contains {len(extra)} untracked sources")
        for pack_size in sorted(set(args.pack_sizes)):
            for offset in range(0, len(cases), pack_size):
                batch = cases[offset : offset + pack_size]
                prompt, redactions = build_packed_prompt(batch)
                await reset_sacrificial_chat(client, args.notebook_id)
                started = datetime.now(UTC)
                result = await client.chat.ask(args.notebook_id, prompt)
                elapsed_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
                mapped, unmapped = map_references_to_sections(result.answer, result.references, len(batch))
                section_spans = answer_sections(result.answer, len(batch))
                global_thread_ids = unique_threads(result.references, source_to_thread)
                answer_offset_references = sum(
                    getattr(reference, "answer_start_char", None) is not None
                    for reference in result.references
                )
                square_marker_references = sum(
                    f"[{getattr(reference, 'citation_number', '')}]" in result.answer
                    for reference in result.references
                    if getattr(reference, "citation_number", None) is not None
                )
                unicode_marker_references = sum(
                    f"【{getattr(reference, 'citation_number', '')}】" in result.answer
                    for reference in result.references
                    if getattr(reference, "citation_number", None) is not None
                )
                rows = []
                local_started = datetime.now(UTC)
                for index, case in enumerate(batch, 1):
                    thread_ids = unique_threads(mapped[index], source_to_thread)
                    expected = set(case["expectedThreadIds"])
                    section = result.answer[slice(*section_spans[index])] if index in section_spans else ""
                    raw_abstained = "NO MATCH" in section.upper() and not thread_ids
                    raw_top1 = bool(thread_ids and thread_ids[0] in expected)
                    candidate_hit = any(thread_id in expected for thread_id in thread_ids)
                    semantic_candidates = [
                        {
                            "threadId": thread_id,
                            "title": state.get("threads", {}).get(thread_id, {}).get("title"),
                            "citationRank": rank,
                        }
                        for rank, thread_id in enumerate(thread_ids, 1)
                    ]
                    reranked, local_verification = local_rerank_candidates(
                        case["query"],
                        semantic_candidates,
                        node_path=args.node,
                    )
                    hybrid_thread_ids = [item["threadId"] for item in reranked]
                    hybrid_abstained = bool(local_verification.get("abstained"))
                    hybrid_top1 = bool(
                        hybrid_thread_ids
                        and not hybrid_abstained
                        and hybrid_thread_ids[0] in expected
                    )
                    rows.append({
                        "caseId": case["caseId"],
                        "name": case["name"],
                        "expectation": case["expectation"],
                        "expectedThreadIds": sorted(expected),
                        "mappedThreadIds": thread_ids,
                        "hybridThreadIds": hybrid_thread_ids,
                        "headingPresent": index in section_spans,
                        "candidateHit": candidate_hit if case["expectation"] == "match" else None,
                        "passedRawTop1": raw_top1 if case["expectation"] == "match" else False,
                        "passedHybridTop1": hybrid_top1 if case["expectation"] == "match" else False,
                        "passedTop1": hybrid_top1 if case["expectation"] == "match" else False,
                        "rawAbstained": raw_abstained,
                        "abstained": hybrid_abstained,
                        "localVerification": local_verification,
                        "passedExpectation": hybrid_top1 if case["expectation"] == "match" else hybrid_abstained,
                    })
                local_elapsed_ms = int((datetime.now(UTC) - local_started).total_seconds() * 1000)
                record = {
                    "packSize": pack_size,
                    "batchIndex": (offset // pack_size) + 1,
                    "questions": len(batch),
                    "elapsedMs": elapsed_ms,
                    "localVerificationElapsedMs": local_elapsed_ms,
                    "wallElapsedMs": elapsed_ms + local_elapsed_ms,
                    "queryRedactions": redactions,
                    "answerSha256": hashlib.sha256(result.answer.encode("utf-8")).hexdigest(),
                    "answerChars": len(result.answer),
                    "referenceCount": len(result.references),
                    "unmappedReferenceCount": unmapped,
                    "answerOffsetReferenceCount": answer_offset_references,
                    "squareMarkerReferenceCount": square_marker_references,
                    "unicodeMarkerReferenceCount": unicode_marker_references,
                    "globalReferencedThreadIds": global_thread_ids,
                    "globalExpectedHits": sum(
                        any(thread_id in set(case["expectedThreadIds"]) for thread_id in global_thread_ids)
                        for case in batch
                    ),
                    "isFollowUp": result.is_follow_up,
                    "sections": rows,
                }
                report["results"].append(record)
                atomic_json(args.out.resolve(), report)
                print(
                    f"pack={pack_size} batch={record['batchIndex']} questions={len(batch)} "
                    f"passed={sum(row['passedExpectation'] for row in rows)}/{len(rows)} "
                    f"elapsedMs={elapsed_ms}",
                    flush=True,
                )
    summaries = []
    for pack_size in sorted(set(args.pack_sizes)):
        batches = [item for item in report["results"] if item["packSize"] == pack_size]
        rows = [row for batch in batches for row in batch["sections"]]
        latencies = [float(batch["elapsedMs"]) for batch in batches]
        wall_latencies = [float(batch.get("wallElapsedMs") or batch["elapsedMs"]) for batch in batches]
        total_ms = sum(latencies)
        wall_total_ms = sum(wall_latencies)
        summaries.append({
            "packSize": pack_size,
            "batches": len(batches),
            "questions": len(rows),
            "passedExpectation": sum(bool(row["passedExpectation"]) for row in rows),
            "rawTop1": sum(bool(row.get("passedRawTop1")) for row in rows),
            "hybridTop1": sum(bool(row.get("passedHybridTop1")) for row in rows),
            "candidateHits": sum(bool(row.get("candidateHit")) for row in rows),
            "headingsPresent": sum(bool(row["headingPresent"]) for row in rows),
            "unmappedReferences": sum(batch["unmappedReferenceCount"] for batch in batches),
            "answerOffsetReferences": sum(batch["answerOffsetReferenceCount"] for batch in batches),
            "squareMarkerReferences": sum(batch["squareMarkerReferenceCount"] for batch in batches),
            "unicodeMarkerReferences": sum(batch["unicodeMarkerReferenceCount"] for batch in batches),
            "globalExpectedHits": sum(batch["globalExpectedHits"] for batch in batches),
            "totalElapsedMs": int(total_ms),
            "localVerificationElapsedMs": sum(batch.get("localVerificationElapsedMs") or 0 for batch in batches),
            "wallElapsedMs": int(wall_total_ms),
            "remoteQueriesPerMinute": round((len(rows) * 60_000 / total_ms), 4) if total_ms else None,
            "queriesPerMinute": round((len(rows) * 60_000 / wall_total_ms), 4) if wall_total_ms else None,
            "batchLatencyP50Ms": round(statistics.median(latencies), 2) if latencies else None,
            "batchLatencyP95Ms": round(percentile(latencies, 0.95) or 0, 2),
        })
    report["completedAt"] = now_iso()
    report["summary"] = summaries
    atomic_json(args.out.resolve(), report)
    print(json.dumps({"report": str(args.out.resolve()), "summary": summaries}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
