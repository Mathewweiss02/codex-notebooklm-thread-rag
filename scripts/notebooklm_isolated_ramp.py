#!/usr/bin/env python3
"""Plan and execute a bounded, isolated NotebookLM retrieval ramp.

The default mode is offline planning. Live replica creation requires both
``--apply`` and ``--confirm-isolated-retrieval-replicas``. The persistent CLI
chat profile is rejected, source IDs are never copied between notebooks, and
reports contain hashes and aggregate counters rather than NotebookLM IDs,
queries, answers, or credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from notebooklm import NotebookLMClient

from notebooklm_replica_plan import ReplicaPlanError, build_replica_plan
from notebooklm_thread_search import local_rerank_candidates
from thread_rag_benchmark_contract import normalize_suite, suite_digests


CONTRACT = "notebooklm-isolated-ramp-v1"
REQUIRED_POLICY = "visible-messages-secrets-redacted-v4"
REQUIRED_ROLE = "retrieval"
REQUIRED_CONVERSATION_POLICY = "dedicated-retrieval-disposable-v1"
TITLE_LIMIT = 180
DEFAULT_LIMIT = 4


class RampError(RuntimeError):
    """A fail-closed ramp error whose message is safe to surface."""


@dataclass(frozen=True)
class Replica:
    ordinal: int
    notebook_id: str
    state_path: Path
    source_to_thread: dict[str, str]
    source_titles: frozenset[str]
    source_fingerprint: str
    existing: bool


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


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_error(error: BaseException) -> dict[str, Any]:
    """Return diagnostics without retaining a remote error message."""

    message = str(error)
    return {
        "type": type(error).__name__,
        "messageSha256": digest(message),
        "messageChars": len(message),
    }


def safe_title(value: str) -> str:
    title = re.sub(r"[^A-Za-z0-9._ -]+", "-", value).strip(" .-")
    if not title:
        raise RampError("replica title is empty after normalization")
    return title[:TITLE_LIMIT]


def validate_retrieval_config(config: dict[str, Any], state_path: Path) -> None:
    if str(config.get("NotebookRole") or "") != REQUIRED_ROLE:
        raise RampError("isolated ramp requires NotebookRole=retrieval")
    if str(config.get("ConversationPolicy") or "") != REQUIRED_CONVERSATION_POLICY:
        raise RampError("isolated ramp requires the disposable retrieval conversation policy")
    if config.get("DisposableSearchChat") is not True:
        raise RampError("isolated ramp requires DisposableSearchChat=true")
    if config.get("RejectUntrackedSources") is not True:
        raise RampError("isolated ramp requires RejectUntrackedSources=true")
    if not str(config.get("Profile") or "").strip():
        raise RampError("retrieval config has no auth profile")
    if not state_path.is_file():
        raise RampError(f"retrieval projection state is missing: {state_path}")


def source_entries(state: dict[str, Any]) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    if state.get("policyVersion") != REQUIRED_POLICY:
        raise RampError("state projection policy is not the required redaction policy")
    entries: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    titles: dict[str, str] = {}
    for thread_id, thread in (state.get("threads") or {}).items():
        parts = thread.get("parts") or []
        if not parts:
            raise RampError("a projected thread has no source parts")
        for part in parts:
            title = str(part.get("title") or "")
            file_path = Path(str(part.get("file") or ""))
            if not title or not file_path.is_file():
                raise RampError("a projected source part is missing its title or file")
            part_key = f"{thread_id}:p{part.get('part')}"
            prior = titles.setdefault(title, part_key)
            if prior != part_key:
                raise RampError("projected source titles are not unique")
            expected_bytes = int(part.get("bytes") or -1)
            if file_path.stat().st_size != expected_bytes:
                raise RampError("projected source size drift detected")
            entries.append((str(thread_id), thread, part))
    if not entries:
        raise RampError("projection state contains no source parts")
    return entries


def state_source_fingerprint(state: dict[str, Any]) -> str:
    entries = source_entries(state)
    lines: list[str] = []
    for thread_id, _thread, part in sorted(entries, key=lambda item: (item[0], str(item[2].get("part")))):
        file_path = Path(str(part["file"]))
        lines.append(
            "\x00".join(
                (
                    thread_id,
                    str(part.get("part")),
                    str(part.get("title")),
                    str(part.get("bytes")),
                    hashlib.sha256(file_path.read_bytes()).hexdigest(),
                )
            )
        )
    return digest("\n".join(lines))


def current_source_map(state: dict[str, Any]) -> tuple[dict[str, str], frozenset[str], str]:
    source_to_thread: dict[str, str] = {}
    titles: set[str] = set()
    for thread_id, _thread, part in source_entries(state):
        source_id = str(part.get("sourceId") or "")
        if not source_id:
            raise RampError("current retrieval state contains an unuploaded source part")
        prior = source_to_thread.setdefault(source_id, thread_id)
        if prior != thread_id:
            raise RampError("one live source ID is assigned to multiple threads")
        titles.add(str(part["title"]))
    return source_to_thread, frozenset(titles), state_source_fingerprint(state)


def clone_state_for_replica(state: dict[str, Any]) -> dict[str, Any]:
    """Make a sync-ready state whose source IDs cannot target the parent notebook."""

    clone = copy.deepcopy(state)
    for key in ("notebookId", "notebookTitle", "lastUploadedAt"):
        clone.pop(key, None)
    for thread in (clone.get("threads") or {}).values():
        for part in thread.get("parts") or []:
            part.pop("sourceId", None)
            part["status"] = "pending"
        thread.pop("notebookId", None)
        thread.pop("previousSources", None)
        thread.pop("uploadRevision", None)
        thread.pop("lastUploadedAt", None)
        thread["uploadStatus"] = "pending"
        thread.pop("uploadError", None)
    return clone


def replica_plan(
    *,
    state: dict[str, Any],
    source_limit: int,
    notebook_limit: int,
    existing_notebooks: int,
    pool_sizes: list[int],
    reserve: int,
) -> dict[str, Any]:
    source_count = len(source_entries(state))
    try:
        return build_replica_plan(
            source_parts=source_count,
            source_limit=source_limit,
            notebook_limit=notebook_limit,
            reserve=reserve,
            existing_notebooks=existing_notebooks,
            current_retrieval_notebooks=1,
            pool_sizes=pool_sizes,
        )
    except ReplicaPlanError as error:
        raise RampError("replica capacity plan is unsafe") from error


def validate_live_sources(
    sources: list[Any],
    *,
    expected_titles: frozenset[str],
    expected_count: int,
) -> tuple[dict[str, Any], frozenset[str]]:
    by_id: dict[str, Any] = {}
    titles: set[str] = set()
    for source in sources:
        source_id = str(getattr(source, "id", "") or "")
        title = str(getattr(source, "title", "") or "")
        if not source_id or not title or source_id in by_id or title in titles:
            raise RampError("replica source identity is duplicate or incomplete")
        by_id[source_id] = source
        titles.add(title)
    if len(by_id) != expected_count or frozenset(titles) != expected_titles:
        raise RampError("replica source fingerprint does not match the projection")
    return by_id, frozenset(titles)


def build_cases(path: Path | None, limit: int, full_suite: bool) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if path is None:
        return [], None
    suite = normalize_suite(read_json(path.resolve()))
    cases = list(suite["cases"])
    if not full_suite:
        cases = cases[:limit]
    return cases, {"suiteId": suite["suiteId"], "split": suite["split"], **suite_digests(suite)}


def classify_failure(error: BaseException) -> str:
    name = type(error).__name__.lower()
    text = str(error).lower()
    if "429" in text or "rate" in name or "quota" in text:
        return "rate-limit"
    if "auth" in name or "credential" in text or "unauthorized" in text:
        return "auth"
    if "timeout" in name or "timeout" in text:
        return "timeout"
    return "other"


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


async def reset_disposable_chat(client: NotebookLMClient, notebook_id: str) -> None:
    conversation_id = await client.chat.get_conversation_id(notebook_id)
    if conversation_id:
        await client.chat.delete_conversation(notebook_id, conversation_id)
    client.chat.clear_cache()


async def ask_one(
    client: NotebookLMClient,
    replica: Replica,
    case: dict[str, Any],
    global_source_owners: dict[str, int],
    node_path: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    started = datetime.now(UTC)
    try:
        await reset_disposable_chat(client, replica.notebook_id)
        result = await asyncio.wait_for(
            client.chat.ask(replica.notebook_id, case["query"]),
            timeout=timeout_seconds,
        )
        references = sorted(result.references, key=lambda item: item.citation_number)
        referenced_threads: list[str] = []
        unmapped = 0
        foreign = 0
        candidates: list[dict[str, Any]] = []
        for reference in references:
            source_id = str(getattr(reference, "source_id", "") or "")
            owner = global_source_owners.get(source_id)
            if owner is not None and owner != replica.ordinal:
                foreign += 1
            thread_id = replica.source_to_thread.get(source_id)
            if not thread_id:
                unmapped += 1
                continue
            if thread_id not in referenced_threads:
                referenced_threads.append(thread_id)
                candidates.append(
                    {
                        "threadId": thread_id,
                        "title": None,
                        "citationRank": len(referenced_threads),
                    }
                )
        state = read_json(replica.state_path)
        for candidate in candidates:
            candidate["title"] = state["threads"].get(candidate["threadId"], {}).get("title")
        expected = set(case["expectedThreadIds"])
        raw_first = referenced_threads[0] if referenced_threads else None
        raw_top1 = case["expectation"] == "match" and raw_first in expected
        candidate_hit = bool(expected.intersection(referenced_threads)) if case["expectation"] == "match" else False
        hybrid_first: str | None = None
        hybrid_abstained = True
        verification_error: dict[str, Any] | None = None
        if candidates:
            try:
                reranked, verification = await asyncio.to_thread(
                    local_rerank_candidates,
                    case["query"],
                    candidates,
                    node_path=node_path,
                )
                hybrid_first = reranked[0]["threadId"] if reranked else None
                hybrid_abstained = bool(verification.get("abstained"))
            except Exception as error:  # local verifier failure is a measured failure
                verification_error = safe_error(error)
                hybrid_abstained = True
        hybrid_top1 = case["expectation"] == "match" and not hybrid_abstained and hybrid_first in expected
        passed_expectation = (
            hybrid_top1 if case["expectation"] == "match" else hybrid_abstained
        )
        return {
            "caseId": str(case["caseId"]),
            "replicaOrdinal": replica.ordinal,
            "passedExpectation": passed_expectation,
            "candidateHit": candidate_hit,
            "rawTop1": raw_top1,
            "hybridTop1": hybrid_top1,
            "rawAbstained": raw_first is None,
            "hybridAbstained": hybrid_abstained,
            "sourceScopePass": unmapped == 0 and foreign == 0,
            "unmappedReferenceCount": unmapped,
            "foreignReferenceCount": foreign,
            "referenceCount": len(references),
            "answerSha256": digest(str(result.answer)),
            "answerChars": len(str(result.answer)),
            "elapsedMs": int((datetime.now(UTC) - started).total_seconds() * 1000),
            "verificationError": verification_error,
            "error": None,
        }
    except Exception as error:
        return {
            "caseId": str(case["caseId"]),
            "replicaOrdinal": replica.ordinal,
            "passedExpectation": False,
            "candidateHit": False,
            "rawTop1": False,
            "hybridTop1": False,
            "rawAbstained": False,
            "hybridAbstained": False,
            "sourceScopePass": False,
            "unmappedReferenceCount": 0,
            "foreignReferenceCount": 0,
            "referenceCount": 0,
            "answerSha256": None,
            "answerChars": 0,
            "elapsedMs": int((datetime.now(UTC) - started).total_seconds() * 1000),
            "verificationError": None,
            "error": safe_error(error),
            "failureClass": classify_failure(error),
        }


async def run_queries(
    client: NotebookLMClient,
    replicas: list[Replica],
    cases: list[dict[str, Any]],
    *,
    runs: int,
    node_path: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    if not cases:
        return {"caseCount": 0, "runs": runs, "results": [], "summary": {}}
    notebook_owners: dict[str, int] = {}
    for replica in replicas:
        notebook_id = str(replica.notebook_id or "")
        if not notebook_id:
            raise RampError("isolated replica is missing a notebook identity")
        prior = notebook_owners.setdefault(notebook_id, replica.ordinal)
        if prior != replica.ordinal:
            raise RampError("query wave contains duplicate notebook identities")
    global_source_owners: dict[str, int] = {}
    for replica in replicas:
        for source_id in replica.source_to_thread:
            owner = global_source_owners.setdefault(source_id, replica.ordinal)
            if owner != replica.ordinal:
                raise RampError("source IDs overlap between isolated replicas")
    results: list[dict[str, Any]] = []
    for run_number in range(1, runs + 1):
        for offset in range(0, len(cases), len(replicas)):
            wave = cases[offset : offset + len(replicas)]
            tasks = [
                ask_one(
                    client,
                    replicas[index],
                    case,
                    global_source_owners,
                    node_path,
                    timeout_seconds,
                )
                for index, case in enumerate(wave)
            ]
            results.extend(await asyncio.gather(*tasks))
    latencies = [float(item["elapsedMs"]) for item in results]
    errors = [item for item in results if item.get("error")]
    matches = [item for item, case in zip(results, cases * runs) if case["expectation"] == "match"]
    summary = {
        "total": len(results),
        "passedExpectation": sum(bool(item["passedExpectation"]) for item in results),
        "candidateRecall": sum(bool(item["candidateHit"]) for item in matches),
        "rawTop1": sum(bool(item["rawTop1"]) for item in matches),
        "hybridTop1": sum(bool(item["hybridTop1"]) for item in matches),
        "matchCases": len(matches),
        "sourceScopeFailures": sum(not bool(item["sourceScopePass"]) for item in results),
        "crossTalkReferenceCount": sum(int(item["foreignReferenceCount"]) for item in results),
        "errorCount": len(errors),
        "rateLimitErrors": sum(item.get("failureClass") == "rate-limit" for item in errors),
        "authErrors": sum(item.get("failureClass") == "auth" for item in errors),
        "timeoutErrors": sum(item.get("failureClass") == "timeout" for item in errors),
        "latencyMs": {
            "p50": round(percentile(latencies, 0.50) or 0, 2),
            "p95": round(percentile(latencies, 0.95) or 0, 2),
            "max": round(max(latencies), 2) if latencies else None,
        },
    }
    return {"caseCount": len(cases), "runs": runs, "results": results, "summary": summary}


def run_sync_upload(state_path: Path, profile: str, notebook_id: str, sync_script: Path) -> None:
    command = [
        sys.executable,
        str(sync_script),
        "--state",
        str(state_path),
        "--profile",
        profile,
        "--notebook-id",
        notebook_id,
        "--swap-old",
        "--reject-untracked-sources",
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise RampError(f"replica source synchronization failed ({completed.returncode})")


async def create_and_sync_replica(
    client: NotebookLMClient,
    *,
    ordinal: int,
    title: str,
    source_state: dict[str, Any],
    profile: str,
    work_root: Path,
    sync_script: Path,
    created_ids: list[str],
) -> tuple[Replica, Any]:
    notebook = await client.notebooks.create(title)
    # Register immediately so a failed upload or lineage check cannot leak a
    # newly created NotebookLM notebook during cleanup.
    created_ids.append(notebook.id)
    replica_dir = work_root / f"replica-{ordinal:02d}"
    replica_dir.mkdir(parents=True, exist_ok=True)
    clone_path = replica_dir / "state.json"
    atomic_json(clone_path, clone_state_for_replica(source_state))
    try:
        await asyncio.to_thread(run_sync_upload, clone_path, profile, notebook.id, sync_script)
        cloned_state = read_json(clone_path)
        source_to_thread, titles, fingerprint = current_source_map(cloned_state)
        live_sources = await client.sources.list(notebook.id, strict=True)
        validate_live_sources(
            live_sources,
            expected_titles=titles,
            expected_count=len(source_to_thread),
        )
        if fingerprint != state_source_fingerprint(source_state):
            raise RampError("replica local source fingerprint differs from the parent")
        return (
            Replica(
                ordinal=ordinal,
                notebook_id=notebook.id,
                state_path=clone_path,
                source_to_thread=source_to_thread,
                source_titles=titles,
                source_fingerprint=fingerprint,
                existing=False,
            ),
            notebook,
        )
    except Exception:
        raise


async def delete_notebooks(client: NotebookLMClient, notebook_ids: list[str]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for notebook_id in notebook_ids:
        try:
            await client.notebooks.delete(notebook_id)
        except Exception as error:
            errors.append(safe_error(error))
    return errors


async def live_apply(args: argparse.Namespace, config: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    pool_size = args.pool_size
    if pool_size < 1:
        raise RampError("pool size must be positive")
    state_path = Path(args.state).resolve()
    source_to_thread, titles, fingerprint = current_source_map(state)
    work_root = Path(args.work_root).expanduser().resolve() / args.run_id
    work_root.mkdir(parents=True, exist_ok=True)
    sync_script = Path(args.sync_script).resolve()
    if not sync_script.is_file():
        raise RampError("sync script is missing")
    created_ids: list[str] = []
    cleanup_errors: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "contractVersion": CONTRACT,
        "startedAt": now_iso(),
        "mode": "live-apply",
        "runId": args.run_id,
        "profile": str(config["Profile"]),
        "poolSize": pool_size,
        "sourcePartCount": len(source_to_thread),
        "sourceFingerprint": fingerprint,
        "replicas": [],
        "errors": [],
    }
    try:
        async with NotebookLMClient.from_storage(profile=str(config["Profile"]), chat_timeout=args.chat_timeout) as client:
            notebooks = await client.notebooks.list()
            limits = await client.settings.get_account_limits()
            source_limit = int(getattr(limits, "source_limit", 0) or 0)
            notebook_limit = int(getattr(limits, "notebook_limit", 0) or 0)
            plan = replica_plan(
                state=state,
                source_limit=source_limit,
                notebook_limit=notebook_limit,
                existing_notebooks=len(notebooks),
                pool_sizes=[pool_size],
                reserve=int(config.get("SourceReserve") or 1),
            )
            report["capacityPlan"] = plan["plans"][0]
            configured_id = str(config.get("NotebookId") or "")
            matches = [item for item in notebooks if item.id == configured_id or item.id.startswith(configured_id)]
            if len(matches) != 1:
                raise RampError("configured retrieval notebook could not be uniquely resolved")
            target = matches[0]
            target_sources = await client.sources.list(target.id, strict=True)
            target_by_id, target_titles = validate_live_sources(
                target_sources,
                expected_titles=titles,
                expected_count=len(source_to_thread),
            )
            target_map = {source_id: thread_id for source_id, thread_id in source_to_thread.items() if source_id in target_by_id}
            if len(target_map) != len(source_to_thread):
                raise RampError("configured retrieval notebook source lineage is incomplete")
            replicas = [
                Replica(
                    ordinal=0,
                    notebook_id=target.id,
                    state_path=state_path,
                    source_to_thread=target_map,
                    source_titles=target_titles,
                    source_fingerprint=fingerprint,
                    existing=True,
                )
            ]
            for ordinal in range(1, pool_size):
                title_text = safe_title(f"Codex RAG isolated retrieval {args.run_id}-{ordinal:02d}")
                replica, notebook = await create_and_sync_replica(
                    client,
                    ordinal=ordinal,
                    title=title_text,
                    source_state=state,
                    profile=str(config["Profile"]),
                    work_root=work_root,
                    sync_script=sync_script,
                    created_ids=created_ids,
                )
                replicas.append(replica)
            report["replicaCount"] = len(replicas)
            report["createdReplicaCount"] = len(created_ids)
            report["replicaFingerprints"] = [
                {
                    "ordinal": replica.ordinal,
                    "existing": replica.existing,
                    "sourceCount": len(replica.source_to_thread),
                    "sourceFingerprint": replica.source_fingerprint,
                    "notebookIdSha256": digest(replica.notebook_id),
                }
                for replica in replicas
            ]
            cases, suite_info = build_cases(args.cases, args.limit, args.full_suite)
            report["suite"] = suite_info
            if cases:
                report["queryEvidence"] = await run_queries(
                    client,
                    replicas,
                    cases,
                    runs=args.runs,
                    node_path=args.node,
                    timeout_seconds=args.query_timeout,
                )
            histories: list[dict[str, Any]] = []
            for replica in replicas:
                try:
                    conversation_id = await client.chat.get_conversation_id(replica.notebook_id)
                    history = await client.chat.get_history(replica.notebook_id)
                    histories.append(
                        {
                            "ordinal": replica.ordinal,
                            "conversationIdSha256": digest(str(conversation_id)) if conversation_id else None,
                            "historyCount": len(history or []),
                        }
                    )
                except Exception as error:
                    histories.append({"ordinal": replica.ordinal, "error": safe_error(error)})
            report["conversationEvidence"] = {
                "replicaCount": len(histories),
                "distinctConversationHashes": len({item.get("conversationIdSha256") for item in histories if item.get("conversationIdSha256")}),
                "histories": histories,
            }
            if args.cleanup:
                cleanup_errors = await delete_notebooks(client, created_ids)
                report["cleanedUp"] = len(created_ids) - len(cleanup_errors)
            else:
                report["cleanedUp"] = 0
    except Exception as error:
        report["errors"].append(safe_error(error))
        try:
            async with NotebookLMClient.from_storage(profile=str(config["Profile"]), chat_timeout=args.chat_timeout) as cleanup_client:
                cleanup_errors = await delete_notebooks(cleanup_client, created_ids)
        except Exception as cleanup_error:
            cleanup_errors.append(safe_error(cleanup_error))
    report["cleanupErrors"] = cleanup_errors
    report["completedAt"] = now_iso()
    report["status"] = "pass" if not report["errors"] and not cleanup_errors else "fail"
    atomic_json(Path(args.out).resolve(), report)
    print(json.dumps({
        "status": report["status"],
        "poolSize": pool_size,
        "createdReplicaCount": report.get("createdReplicaCount", 0),
        "cleanedUp": report.get("cleanedUp", 0),
        "errorCount": len(report["errors"]),
        "cleanupErrorCount": len(cleanup_errors),
        "report": str(Path(args.out).resolve()),
    }, indent=2))
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--pool-size", type=int, default=1)
    parser.add_argument("--pool-sizes", nargs="+", type=int, default=[1, 2, 4, 8])
    parser.add_argument("--source-limit", type=int, default=300)
    parser.add_argument("--notebook-limit", type=int, default=500)
    parser.add_argument("--existing-notebooks", type=int, default=1)
    parser.add_argument("--reserve", type=int, default=60)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--full-suite", action="store_true")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--node")
    parser.add_argument("--query-timeout", type=float, default=240.0)
    parser.add_argument("--chat-timeout", type=float, default=300.0)
    parser.add_argument("--sync-script", type=Path, default=Path(__file__).with_name("notebooklm_thread_sync.py"))
    parser.add_argument("--work-root", type=Path, default=Path.home() / ".codex" / "thread-rag" / "isolated-ramp")
    parser.add_argument("--run-id", default=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="allow live replica creation and querying")
    parser.add_argument("--confirm-isolated-retrieval-replicas", action="store_true")
    parser.add_argument("--cleanup", action="store_true", help="delete replicas after a successful evidence run")
    args = parser.parse_args(argv)
    if args.pool_size < 1 or args.runs < 1 or args.limit < 1:
        parser.error("pool size, runs, and limit must be positive")
    if args.full_suite and args.cases is None:
        parser.error("--full-suite requires --cases")
    if args.apply and not args.confirm_isolated_retrieval_replicas:
        parser.error("--apply requires --confirm-isolated-retrieval-replicas")
    if args.cleanup and not args.apply:
        parser.error("--cleanup requires --apply")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config.resolve()
    config = read_json(config_path)
    state_path = (args.state or (Path(str(config.get("ProjectionRoot") or config_path.parent)) / "state.json")).resolve()
    validate_retrieval_config(config, state_path)
    state = read_json(state_path)
    source_entries(state)
    if not args.apply:
        try:
            plan = replica_plan(
                state=state,
                source_limit=args.source_limit,
                notebook_limit=args.notebook_limit,
                existing_notebooks=args.existing_notebooks,
                pool_sizes=args.pool_sizes,
                reserve=args.reserve,
            )
        except RampError as error:
            print(json.dumps({"status": "error", "code": "INVALID_REPLICA_PLAN", "message": str(error)}))
            return 1
        report = {
            "contractVersion": CONTRACT,
            "status": "dry-run",
            "configRole": config["NotebookRole"],
            "sourcePartCount": len(source_entries(state)),
            "sourceFingerprint": state_source_fingerprint(state),
            "plan": plan,
            "liveCreation": "not performed; requires --apply and --confirm-isolated-retrieval-replicas",
            "generatedAt": now_iso(),
        }
        atomic_json(args.out.resolve(), report)
        print(json.dumps({
            "status": report["status"],
            "sourcePartCount": report["sourcePartCount"],
            "poolSizes": plan["poolSizes"],
            "report": str(args.out.resolve()),
        }, indent=2))
        return 0
    report = asyncio.run(live_apply(args, config, state))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
