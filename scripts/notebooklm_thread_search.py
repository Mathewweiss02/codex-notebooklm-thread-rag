#!/usr/bin/env python3
"""Search synchronized Codex task projections and return cited candidate task IDs."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from notebooklm import NotebookLMClient
from redaction_contract import POLICY as REMOTE_REDACTION_POLICY
from redaction_contract import sanitize_remote_text


REQUIRED_POLICY = "visible-messages-secrets-redacted-v4"


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def sanitize_query(value: str) -> tuple[str, int]:
    text, counts = sanitize_remote_text(value)
    return text, sum(counts.values())


def normalized_title(value: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", value or "", flags=re.UNICODE)).strip().casefold()


TITLE_STOP_WORDS = {
    "a", "an", "and", "app", "build", "check", "compare", "conversation", "define",
    "did", "find", "for", "from", "in", "into", "locate", "my", "of", "on", "or",
    "plan", "project", "research", "task", "the", "to", "verify", "was", "where", "which",
    "with",
}


def normalized_concept_tokens(value: str | None) -> set[str]:
    tokens: set[str] = set()
    for token in normalized_title(value).split():
        if len(token) > 3 and token.endswith("ies"):
            token = f"{token[:-3]}y"
        elif len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        if len(token) >= 2 and token not in TITLE_STOP_WORDS:
            tokens.add(token)
    return tokens


def title_query_overlap(query: str | None, title: str | None) -> float:
    title_tokens = normalized_concept_tokens(title)
    if not title_tokens:
        return 0.0
    query_tokens = normalized_concept_tokens(query)
    return round(len(title_tokens & query_tokens) / len(title_tokens), 4)


def exact_title_cue(query: str) -> str | None:
    match = re.search(
        r"\btitled\s+exactly\s+(.+?)(?=,\s*(?:without|with|and|return)\b|\.\s|$)",
        query,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip(" \t\"'") if match else None


def merge_local_ranking(
    candidates: list[dict[str, Any]],
    local_results: list[dict[str, Any]],
    *,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Promote locally verified candidates while retaining semantic provenance."""
    by_id = {item["threadId"]: item for item in candidates}
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for local_rank, local in enumerate(local_results, 1):
        thread_id = local.get("id")
        semantic = by_id.get(thread_id)
        if semantic is None or thread_id in seen:
            continue
        seen.add(thread_id)
        output.append({
            **semantic,
            "semanticRank": semantic.get("semanticRank") or candidates.index(semantic) + 1,
            "localRank": local_rank,
            "localScore": local.get("score"),
            "localCoverage": local.get("coverage"),
            "locallyVerified": True,
        })
    for semantic_rank, semantic in enumerate(candidates, 1):
        if semantic["threadId"] in seen:
            continue
        output.append({
            **semantic,
            "semanticRank": semantic.get("semanticRank") or semantic_rank,
            "localRank": None,
            "localScore": None,
            "localCoverage": None,
            "locallyVerified": False,
        })
    max_local_score = max((float(item.get("localScore") or 0) for item in output), default=0.0)
    title_cue = exact_title_cue(query or "")
    wanted = normalized_title(title_cue) if title_cue else None
    for item in output:
        semantic_score = 1.0 / max(1, int(item["semanticRank"]))
        local_score = float(item.get("localScore") or 0)
        normalized_local_score = local_score / max_local_score if max_local_score else 0.0
        title_overlap = title_query_overlap(query, item.get("title"))
        item["titleQueryOverlap"] = title_overlap
        item["hybridScore"] = round(semantic_score + (1.1 * normalized_local_score) + (1.25 * title_overlap), 6)
        item["exactTitleMatch"] = bool(wanted and normalized_title(item.get("title")) == wanted)
    output.sort(key=lambda item: (
        not item["exactTitleMatch"],
        -item["hybridScore"],
        item["semanticRank"],
        item.get("localRank") or 1_000_000,
    ))
    for final_rank, item in enumerate(output, 1):
        item["finalRank"] = final_rank
    return output


def local_rerank_candidates(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    node_path: str | None = None,
    script_path: Path | None = None,
    timeout_seconds: int = 240,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rerank NotebookLM candidates against authoritative local Codex JSONL files."""
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for semantic_rank, candidate in enumerate(candidates, 1):
        thread_id = candidate.get("threadId")
        if not thread_id or thread_id in seen:
            continue
        seen.add(thread_id)
        unique.append({**candidate, "semanticRank": semantic_rank})
    if not unique:
        return [], {"attempted": False, "reason": "no-semantic-candidates"}
    node = node_path or shutil.which("node")
    if not node:
        raise RuntimeError("Node.js was not found for local candidate verification")
    script = (script_path or Path(__file__).with_name("thread_search.mjs")).resolve()
    if not script.is_file():
        raise FileNotFoundError(f"Local task search script was not found: {script}")
    command = [node, str(script), "--query", query, "--limit", str(len(unique)), "--min-score", "0", "--no-hydrate", "--json"]
    for candidate in unique:
        command.extend(["--thread", candidate["threadId"]])
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else f"exit code {completed.returncode}"
        raise RuntimeError(f"Local candidate verification failed: {detail}")
    try:
        local_report = json.loads(completed.stdout.lstrip("\ufeff"))
    except json.JSONDecodeError as error:
        raise RuntimeError("Local candidate verification returned invalid JSON") from error
    local_results = local_report.get("results") or []
    reranked = merge_local_ranking(unique, local_results, query=query)
    return reranked, {
        "attempted": True,
        "engine": local_report.get("stats", {}).get("engine"),
        "elapsedMs": local_report.get("stats", {}).get("elapsedMs"),
        "filesSearched": local_report.get("stats", {}).get("filesSearched"),
        "candidateCount": len(unique),
        "verifiedCount": sum(1 for item in reranked if item["locallyVerified"]),
    }


def discover_configs(explicit: list[Path], codex_root: Path) -> list[Path]:
    if explicit:
        return [path.resolve() for path in explicit]
    registry_path = codex_root / "thread-rag" / "registry.json"
    registry = read_json(registry_path)
    paths = []
    for item in registry.get("Configs", []):
        if not item.get("ConfigPath"):
            continue
        path = Path(item["ConfigPath"]).resolve()
        role = str(item.get("NotebookRole") or "")
        if not role and path.is_file():
            role = str(read_json(path).get("NotebookRole") or "")
        if role == "retrieval":
            paths.append(path)
    if not paths:
        raise ValueError(f"No registered sync configurations: {registry_path}")
    return paths


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def load_instance(config_path: Path, max_run_age_minutes: int, allow_unmonitored: bool) -> dict[str, Any]:
    config = read_json(config_path)
    if str(config.get("NotebookRole") or "") != "retrieval":
        raise ValueError(f"Automated retrieval requires NotebookRole=retrieval: {config_path}")
    root = Path(config["ProjectionRoot"])
    state_path = root / "state.json"
    state = read_json(state_path)
    if state.get("policyVersion") != REQUIRED_POLICY:
        raise ValueError(f"Policy mismatch for {config_path}")
    runner_path = root / "runner_state.json"
    runner = read_json(runner_path) if runner_path.is_file() else {}
    last_success = parse_time(runner.get("LastSuccessAt"))
    if not allow_unmonitored:
        if last_success is None:
            raise ValueError(f"No successful runner checkpoint for {config_path}")
        age = (datetime.now(UTC) - last_success).total_seconds() / 60
        if age > max_run_age_minutes:
            raise ValueError(f"Runner is stale for {config_path}: {age:.1f} minutes")
    source_to_thread: dict[str, str] = {}
    title_to_part: dict[str, str] = {}
    for thread_id, thread in (state.get("threads") or {}).items():
        if thread.get("uploadRevision") != thread.get("revision"):
            continue
        for part in thread.get("parts") or []:
            part_key = f"{thread_id}:p{part.get('part')}"
            title = str(part.get("title") or "")
            if title:
                owner = title_to_part.setdefault(title, part_key)
                if owner != part_key:
                    raise ValueError(f"Duplicate projected source title in {state_path}")
            source_id = str(part.get("sourceId") or "")
            if source_id:
                owner = source_to_thread.setdefault(source_id, thread_id)
                if owner != thread_id:
                    raise ValueError(f"Duplicate projected source id in {state_path}")
    if not source_to_thread:
        raise ValueError(f"No current uploaded sources in {state_path}")
    return {"configPath": config_path, "config": config, "statePath": state_path, "state": state, "lastSuccess": last_success, "sourceToThread": source_to_thread}


async def search_instance(instance: dict[str, Any], query: str, allow_followup: bool, limit: int) -> dict[str, Any]:
    config = instance["config"]
    profile = config["Profile"]
    notebook_id = config["NotebookId"]
    disposable = config.get("DisposableSearchChat") is True
    notebook_role = str(config.get("NotebookRole") or "")
    if disposable and notebook_role != "retrieval":
        raise ValueError(f"Config {instance['configPath']} must declare NotebookRole=retrieval before automated chat deletion")
    if not disposable and not allow_followup:
        raise ValueError(f"Config {instance['configPath']} is not marked DisposableSearchChat=true")
    async with NotebookLMClient.from_storage(profile=profile, chat_timeout=240.0) as client:
        live_ids = {source.id for source in await client.sources.list(notebook_id, strict=True)}
        expected_ids = set(instance["sourceToThread"])
        missing = expected_ids - live_ids
        if missing:
            raise ValueError(f"Notebook is missing {len(missing)} state-linked sources")
        extra = live_ids - expected_ids
        if config.get("RejectUntrackedSources") is True and extra:
            raise ValueError(f"Dedicated retrieval notebook contains {len(extra)} untracked sources")
        if disposable:
            conversation_id = await client.chat.get_conversation_id(notebook_id)
            if conversation_id:
                await client.chat.delete_conversation(notebook_id, conversation_id)
            client.chat.clear_cache()
        # Keep the retrieval prompt identical to the benchmark surface. Additional
        # meta-instructions measurably changed citation ordering on related-task decoys.
        result = await client.chat.ask(notebook_id, query)
        references = sorted(result.references, key=lambda item: item.citation_number)
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for reference in references:
            thread_id = instance["sourceToThread"].get(reference.source_id)
            if not thread_id or thread_id in seen:
                continue
            seen.add(thread_id)
            thread = instance["state"]["threads"].get(thread_id, {})
            candidates.append({
                "threadId": thread_id,
                "title": thread.get("title"),
                "citationRank": reference.citation_number,
                "sourceId": reference.source_id,
            })
            if len(candidates) >= limit:
                break
        return {
            "device": config["Device"],
            "profile": profile,
            "lastRunnerSuccess": instance["lastSuccess"].isoformat().replace("+00:00", "Z") if instance["lastSuccess"] else None,
            "quietMinutes": config.get("QuietMinutes"),
            "hardMaxHours": config.get("HardMaxHours"),
            "referenceCount": len(references),
            "answerSha256": hashlib.sha256(result.answer.encode("utf-8")).hexdigest(),
            "answerChars": len(result.answer),
            "candidates": candidates,
        }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--config", action="append", type=Path, default=[])
    parser.add_argument("--codex-root", type=Path, default=Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex"))
    parser.add_argument("--max-run-age-minutes", type=int, default=45)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--allow-unmonitored", action="store_true")
    parser.add_argument("--allow-followup", action="store_true")
    parser.add_argument("--no-local-rerank", action="store_true", help="Diagnostic only: preserve raw NotebookLM citation order")
    parser.add_argument("--node", help="Node.js executable used for local candidate verification")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be >= 1")
    safe_query, redactions = sanitize_query(args.query)
    query_hash = hashlib.sha256(safe_query.encode("utf-8")).hexdigest()
    report: dict[str, Any] = {"startedAt": now_iso(), "querySha256": query_hash, "queryRedactions": redactions, "queryRedactionPolicy": REMOTE_REDACTION_POLICY, "instances": [], "errors": []}
    configs = discover_configs(args.config, args.codex_root)
    for config_path in configs:
        try:
            instance = load_instance(config_path, args.max_run_age_minutes, args.allow_unmonitored)
            report["instances"].append(await search_instance(instance, safe_query, args.allow_followup, args.limit))
        except Exception as error:
            report["errors"].append({"config": str(config_path), "error": f"{type(error).__name__}: {error}"})
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for instance in report["instances"]:
        for candidate in instance["candidates"]:
            key = (instance["device"], candidate["threadId"])
            score = 1.0 / max(1, candidate["citationRank"])
            merged[key] = {**candidate, "device": instance["device"], "score": round(score, 6)}
    semantic_candidates = sorted(merged.values(), key=lambda item: (-item["score"], item["device"], item["threadId"]))
    report["semanticCandidates"] = semantic_candidates
    if args.no_local_rerank:
        report["candidates"] = [{**item, "semanticRank": rank, "finalRank": rank, "locallyVerified": False} for rank, item in enumerate(semantic_candidates, 1)]
        report["localVerification"] = {"attempted": False, "reason": "explicitly-disabled"}
    else:
        try:
            report["candidates"], report["localVerification"] = local_rerank_candidates(safe_query, semantic_candidates, node_path=args.node)
        except Exception as error:
            report["candidates"] = []
            report["localVerification"] = {"attempted": True, "error": f"{type(error).__name__}: {error}"}
            report["errors"].append({"config": "local-authority", "error": report["localVerification"]["error"]})
    report["completedAt"] = now_iso()
    output = args.out or args.codex_root / "thread-rag" / "search-runs" / f"search-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    atomic_json(output, report)
    print(json.dumps({"querySha256": query_hash, "instances": len(report["instances"]), "errors": report["errors"], "candidates": report["candidates"], "report": str(output)}, indent=2))
    usable = bool(report["candidates"]) if args.no_local_rerank else any(item.get("locallyVerified") for item in report["candidates"])
    return 0 if report["instances"] and usable else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
