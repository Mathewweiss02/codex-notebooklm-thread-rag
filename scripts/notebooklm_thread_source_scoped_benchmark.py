#!/usr/bin/env python3
"""Benchmark the opt-in local-first/source-scoped retrieval route.

This is deliberately separate from the global semantic benchmark. It selects a
bounded local candidate surface, asks only the mapped current NotebookLM
sources, then applies the same local authority and abstention contract. It is
development-only so a holdout cannot be spent accidentally.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from notebooklm import NotebookLMClient  # noqa: E402
from notebooklm_thread_search import (  # noqa: E402
    local_candidate_surface,
    local_rerank_candidates,
    sanitize_query,
)
from redaction_contract import summarize_error  # noqa: E402
from thread_rag_benchmark_contract import (  # noqa: E402
    normalize_suite,
    suite_digests,
    wilson_interval,
)


CONTRACT = "source-scoped-hybrid-development-v1"


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--notebook-id", required=True)
    parser.add_argument("--candidate-width", type=int, default=80)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--threshold", type=float, default=0.975)
    parser.add_argument("--max-semantic-attempts", type=int, default=1)
    parser.add_argument("--min-semantic-candidates", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--node")
    parser.add_argument("--codex-root", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--confirm-disposable-retrieval-notebook",
        action="store_true",
        help="Required acknowledgement because every case resets the retrieval conversation",
    )
    parser.add_argument("--allow-untracked-sources", action="store_true")
    args = parser.parse_args()
    if not args.confirm_disposable_retrieval_notebook:
        parser.error("--confirm-disposable-retrieval-notebook is required")
    if not 1 <= args.candidate_width <= 200:
        parser.error("--candidate-width must be between 1 and 200")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between 0 and 1")
    if not 1 <= args.max_semantic_attempts <= 3:
        parser.error("--max-semantic-attempts must be between 1 and 3")
    if not 1 <= args.min_semantic_candidates <= 10:
        parser.error("--min-semantic-candidates must be between 1 and 10")
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    return args


def build_source_map(state: dict[str, Any]) -> tuple[dict[str, str], dict[str, list[str]]]:
    source_to_thread: dict[str, str] = {}
    thread_to_sources: dict[str, list[str]] = {}
    for thread_id, thread in (state.get("threads") or {}).items():
        for part in thread.get("parts") or []:
            source_id = str(part.get("sourceId") or "")
            if not source_id:
                raise ValueError(f"Thread {thread_id} has an unuploaded part")
            owner = source_to_thread.setdefault(source_id, thread_id)
            if owner != thread_id:
                raise ValueError("One live source id is assigned to multiple projected tasks")
            thread_to_sources.setdefault(thread_id, []).append(source_id)
    if not source_to_thread:
        raise ValueError("Projection state contains no uploaded sources")
    return source_to_thread, thread_to_sources


async def reset_sacrificial_chat(client: NotebookLMClient, notebook_id: str) -> None:
    conversation_id = await client.chat.get_conversation_id(notebook_id)
    if conversation_id:
        await client.chat.delete_conversation(notebook_id, conversation_id)
    client.chat.clear_cache()


def select_scope(
    query: str,
    source_to_thread: dict[str, str],
    thread_to_sources: dict[str, list[str]],
    *,
    width: int,
    node_path: str | None,
    codex_root: Path | None,
    timeout: int,
) -> dict[str, Any]:
    surface = local_candidate_surface(
        query,
        width,
        node_path=node_path,
        codex_root=codex_root,
        timeout_seconds=timeout,
        thread_ids=set(thread_to_sources),
        min_score=0,
    )
    selected_threads = [
        item["threadId"]
        for item in surface.get("candidates") or []
        if item.get("threadId") in thread_to_sources
    ][:width]
    source_ids = [
        source_id
        for thread_id in selected_threads
        for source_id in thread_to_sources[thread_id]
    ]
    if any(source_to_thread.get(source_id) not in selected_threads for source_id in source_ids):
        raise ValueError("local source scope contains an unmapped source")
    return {
        "candidateWidth": width,
        "localCandidateCount": len(selected_threads),
        "sourceCount": len(source_ids),
        "localElapsedMs": surface.get("elapsedMs"),
        "sourceIds": source_ids,
    }


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 3)


async def main() -> int:
    args = parse_args()
    state = read_json(args.state.resolve())
    source_to_thread, thread_to_sources = build_source_map(state)
    suite = normalize_suite(read_json(args.cases.resolve()))
    if suite["split"] != "development":
        raise ValueError("source-scoped benchmark is development-only; holdout details must remain sealed")
    cases = suite["cases"][: args.limit] if args.limit is not None else suite["cases"]
    report: dict[str, Any] = {
        "contractVersion": CONTRACT,
        "startedAt": now_iso(),
        "profile": args.profile,
        "notebookId": args.notebook_id,
        "suiteId": suite["suiteId"],
        "split": suite["split"],
        **suite_digests(suite),
        "retrievalMode": "local-first-source-scoped",
        "candidateWidth": args.candidate_width,
        "maxSemanticAttempts": args.max_semantic_attempts,
        "minSemanticCandidates": args.min_semantic_candidates,
        "caseCount": len(cases),
        "results": [],
    }
    async with NotebookLMClient.from_storage(profile=args.profile, chat_timeout=args.timeout) as client:
        live_ids = {source.id for source in await client.sources.list(args.notebook_id, strict=True)}
        missing = sorted(set(source_to_thread) - live_ids)
        if missing:
            raise ValueError(f"Live notebook is missing {len(missing)} state-linked sources")
        extra = sorted(live_ids - set(source_to_thread))
        if extra and not args.allow_untracked_sources:
            raise ValueError(f"Dedicated retrieval notebook contains {len(extra)} untracked sources")
        for index, case in enumerate(cases, 1):
            started = time.perf_counter()
            safe_query, redaction_count = sanitize_query(case["query"])
            record: dict[str, Any] = {
                "caseId": case["caseId"],
                "name": case["name"],
                "expectation": case["expectation"],
                "stratum": case["stratum"],
                "expectedThreadIds": sorted(case.get("expectedThreadIds") or []),
                "queryRedactions": redaction_count,
                "sourceScopeValid": True,
                "remoteCandidateHit": False,
                "remoteTop1": False,
                "hybridTop1": False,
                "hybridAbstained": True,
                "attempts": [],
            }
            try:
                scope = select_scope(
                    safe_query,
                    source_to_thread,
                    thread_to_sources,
                    width=args.candidate_width,
                    node_path=args.node,
                    codex_root=args.codex_root,
                    timeout=args.timeout,
                )
                allowed_source_ids = set(scope["sourceIds"])
                record["sourceScope"] = {key: value for key, value in scope.items() if key != "sourceIds"}
                by_thread: dict[str, dict[str, Any]] = {}
                out_of_scope_references = 0
                for attempt in range(1, args.max_semantic_attempts + 1):
                    await reset_sacrificial_chat(client, args.notebook_id)
                    try:
                        if not allowed_source_ids:
                            break
                        result = await client.chat.ask(
                            args.notebook_id,
                            safe_query,
                            source_ids=list(scope["sourceIds"]),
                        )
                    except Exception as error:
                        record["attempts"].append({"attempt": attempt, "error": summarize_error(error)})
                        continue
                    references = sorted(result.references, key=lambda item: item.citation_number)
                    record["attempts"].append({
                        "attempt": attempt,
                        "referenceCount": len(references),
                        "answerSha256": hashlib.sha256(result.answer.encode("utf-8")).hexdigest(),
                        "answerChars": len(result.answer),
                        "isFollowUp": result.is_follow_up,
                    })
                    for reference in references:
                        if reference.source_id not in allowed_source_ids:
                            out_of_scope_references += 1
                            continue
                        thread_id = source_to_thread.get(reference.source_id)
                        if not thread_id:
                            continue
                        candidate = by_thread.setdefault(thread_id, {
                            "threadId": thread_id,
                            "citationRank": reference.citation_number,
                            "firstAttempt": attempt,
                        })
                        candidate["citationRank"] = min(candidate["citationRank"], reference.citation_number)
                    if len(by_thread) >= args.min_semantic_candidates:
                        break
                record["sourceScopeValid"] = out_of_scope_references == 0
                referenced_threads = [
                    item["threadId"]
                    for item in sorted(
                        by_thread.values(),
                        key=lambda item: (item["citationRank"], item["firstAttempt"], item["threadId"]),
                    )
                ]
                expected = set(case.get("expectedThreadIds") or [])
                record["remoteCandidateThreadCount"] = len(referenced_threads)
                record["remoteCandidateHit"] = any(thread_id in expected for thread_id in referenced_threads)
                record["remoteTop1"] = bool(referenced_threads and referenced_threads[0] in expected and record["sourceScopeValid"])
                semantic_candidates = [
                    {"threadId": thread_id, "title": state["threads"].get(thread_id, {}).get("title"), "citationRank": rank}
                    for rank, thread_id in enumerate(referenced_threads, 1)
                ]
                if semantic_candidates:
                    ranked, verification = local_rerank_candidates(
                        safe_query,
                        semantic_candidates,
                        node_path=args.node,
                        timeout_seconds=args.timeout,
                    )
                    hybrid_threads = [item["threadId"] for item in ranked]
                    record["hybridAbstained"] = bool(verification.get("abstained")) or not bool(hybrid_threads) or not record["sourceScopeValid"]
                    record["hybridTop1"] = bool(hybrid_threads and not record["hybridAbstained"] and hybrid_threads[0] in expected)
                    record["hybridExpectedRank"] = next((rank for rank, thread_id in enumerate(hybrid_threads, 1) if thread_id in expected), None)
                    record["localVerificationReason"] = (verification.get("confidence") or {}).get("reason")
                record["semanticExpectedRank"] = next((rank for rank, thread_id in enumerate(referenced_threads, 1) if thread_id in expected), None)
                record["semanticCandidateThreadIds"] = referenced_threads
                record["hybridThreadIds"] = [item["threadId"] for item in ranked] if semantic_candidates else []
                record["outOfScopeReferenceCount"] = out_of_scope_references
            except Exception as error:
                record["error"] = summarize_error(error)
            record["elapsedMs"] = round((time.perf_counter() - started) * 1000, 3)
            report["results"].append(record)
            atomic_json(args.out.resolve(), report)
            passed = record["hybridTop1"] if case["expectation"] == "match" else record["hybridAbstained"]
            print(f"[{index}/{len(cases)}] {'PASS' if passed else 'FAIL'} {record['elapsedMs']}ms", flush=True)
    positives = [item for item in report["results"] if item["expectation"] == "match"]
    negatives = [item for item in report["results"] if item["expectation"] == "no_match"]
    candidate_hits = sum(bool(item.get("remoteCandidateHit")) for item in positives)
    hybrid_hits = sum(bool(item.get("hybridTop1")) for item in positives)
    false_positives = sum(not bool(item.get("hybridAbstained")) for item in negatives)
    false_negatives = len(positives) - candidate_hits
    latencies = [float(item["elapsedMs"]) for item in report["results"] if isinstance(item.get("elapsedMs"), (int, float))]
    candidate_rate = candidate_hits / len(positives) if positives else 0.0
    hybrid_rate = hybrid_hits / len(positives) if positives else 0.0
    false_positive_rate = false_positives / len(negatives) if negatives else 0.0
    false_negative_rate = false_negatives / len(positives) if positives else 0.0
    gates = {
        "candidateRecall100": candidate_hits == len(positives),
        "hybridTop1": hybrid_rate >= args.threshold,
        "falsePositiveRate": false_positive_rate <= 0.05,
        "falseNegativeRate": false_negative_rate <= 0.05,
        "scopeValid": all(bool(item.get("sourceScopeValid")) for item in report["results"]),
        "errors": not any(item.get("error") for item in report["results"]),
    }
    report["completedAt"] = now_iso()
    report["summary"] = {
        "positiveTotal": len(positives),
        "negativeTotal": len(negatives),
        "semanticCandidateRecall": {"successes": candidate_hits, "total": len(positives), "rate": round(candidate_rate, 4), "wilson95": wilson_interval(candidate_hits, len(positives))},
        "hybridTop1": {"successes": hybrid_hits, "total": len(positives), "rate": round(hybrid_rate, 4), "wilson95": wilson_interval(hybrid_hits, len(positives))},
        "falsePositiveRate": {"successes": false_positives, "total": len(negatives), "rate": round(false_positive_rate, 4), "wilson95": wilson_interval(false_positives, len(negatives))},
        "falseNegativeRate": {"successes": false_negatives, "total": len(positives), "rate": round(false_negative_rate, 4), "wilson95": wilson_interval(false_negatives, len(positives))},
        "latencyMs": {"count": len(latencies), "p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95), "max": max(latencies) if latencies else None},
        "scopeViolations": sum(not bool(item.get("sourceScopeValid")) for item in report["results"]),
        "errors": sum(bool(item.get("error")) for item in report["results"]),
    }
    report["gates"] = gates
    report["passed"] = all(gates.values())
    atomic_json(args.out.resolve(), report)
    print(json.dumps({"report": str(args.out.resolve()), "summary": report["summary"], "gates": gates, "passed": report["passed"]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
