#!/usr/bin/env python3
"""Upload validated Codex thread projections to NotebookLM with guarded revision swaps."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from notebooklm import NotebookLMClient


REQUIRED_POLICY = "visible-messages-secrets-redacted-v6"


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    for attempt in range(10):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.05 * (attempt + 1))


def validate_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    policy = state.get("policyVersion")
    if policy != REQUIRED_POLICY:
        raise ValueError(f"Refusing policy {policy!r}; required {REQUIRED_POLICY!r}")
    threads = state.get("threads")
    if not isinstance(threads, dict) or not threads:
        raise ValueError("State contains no projected threads")
    validated: list[dict[str, Any]] = []
    for thread_id, thread in threads.items():
        if thread.get("policyVersion") != REQUIRED_POLICY:
            raise ValueError(f"Thread {thread_id} has the wrong projection policy")
        if int((thread.get("stats") or {}).get("overflowVisibleLines") or 0) != 0:
            raise ValueError(f"Thread {thread_id} skipped an oversized visible message")
        parts = thread.get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError(f"Thread {thread_id} has no source parts")
        for part in parts:
            file_path = Path(part.get("file") or "")
            if not file_path.is_file():
                raise ValueError(f"Missing projected part for {thread_id}: {file_path}")
            if file_path.stat().st_size != int(part.get("bytes") or -1):
                raise ValueError(f"Projected part size drift for {thread_id}: {file_path}")
            if not part.get("title"):
                raise ValueError(f"Projected part lacks a source title for {thread_id}")
        validated.append(thread)
    return validated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path, help="Projection state.json")
    parser.add_argument("--profile", required=True, help="NotebookLM auth profile")
    parser.add_argument("--notebook-id", help="Existing target notebook id")
    parser.add_argument("--notebook-title", help="Exact notebook title to find or create")
    parser.add_argument("--create-notebook", action="store_true", help="Create the exact title when absent")
    parser.add_argument("--swap-old", action="store_true", help="Delete only lineage-linked prior revision sources after the new revision is ready")
    parser.add_argument("--thread", action="append", default=[], help="Limit to a task id or prefix; repeatable")
    parser.add_argument("--max-threads", type=int, help="Limit selected tasks")
    parser.add_argument("--wait-timeout", type=float, default=300.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate-only", action="store_true", help="Validate state and live source lineage without uploads")
    parser.add_argument("--prune-known-orphans", action="store_true", help="Delete only unreferenced live sources whose titles match known prior lineage")
    args = parser.parse_args()
    if not args.notebook_id and not args.notebook_title:
        parser.error("use --notebook-id or --notebook-title")
    if args.create_notebook and not args.notebook_title:
        parser.error("--create-notebook requires --notebook-title")
    return args


async def resolve_notebook(client: NotebookLMClient, args: argparse.Namespace):
    notebooks = await client.notebooks.list()
    if args.notebook_id:
        matches = [item for item in notebooks if item.id == args.notebook_id or item.id.startswith(args.notebook_id)]
        if len(matches) != 1:
            raise ValueError(f"Expected one notebook for id {args.notebook_id!r}; found {len(matches)}")
        return matches[0], False
    matches = [item for item in notebooks if item.title == args.notebook_title]
    if len(matches) > 1:
        raise ValueError(f"Multiple notebooks have exact title {args.notebook_title!r}")
    if matches:
        return matches[0], False
    if not args.create_notebook:
        raise ValueError(f"Notebook not found: {args.notebook_title!r}")
    if args.dry_run:
        return None, True
    return await client.notebooks.create(args.notebook_title), True


def select_threads(threads: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected = threads
    if args.thread:
        selected = [
            thread for thread in selected
            if any(str(thread.get("threadId", "")).startswith(prefix) for prefix in args.thread)
        ]
    selected.sort(key=lambda item: (str(item.get("lastProjectedAt") or ""), str(item.get("threadId") or "")))
    if args.max_threads is not None:
        selected = selected[: args.max_threads]
    return selected


def validate_unique_current_lineage(threads: list[dict[str, Any]]) -> None:
    seen_titles: dict[str, str] = {}
    seen_ids: dict[str, str] = {}
    for thread in threads:
        thread_id = str(thread.get("threadId") or "")
        for part in thread.get("parts") or []:
            title = str(part.get("title") or "")
            if title in seen_titles:
                raise ValueError(f"Duplicate projected source title across tasks: {seen_titles[title]} and {thread_id}")
            seen_titles[title] = thread_id
            source_id = part.get("sourceId")
            if not source_id:
                continue
            if source_id in seen_ids:
                raise ValueError(f"Duplicate projected source ID across tasks: {seen_ids[source_id]} and {thread_id}")
            seen_ids[source_id] = thread_id


def known_orphans(threads: list[dict[str, Any]], sources: list[Any]) -> list[Any]:
    referenced_ids: set[str] = set()
    known_prior_titles: set[str] = set()
    for thread in threads:
        for part in thread.get("parts") or []:
            if part.get("sourceId"):
                referenced_ids.add(part["sourceId"])
        for old in thread.get("previousSources") or []:
            if old.get("sourceId"):
                referenced_ids.add(old["sourceId"])
            if old.get("title"):
                known_prior_titles.add(old["title"])
    extras = [source for source in sources if source.id not in referenced_ids]
    unknown = [source for source in extras if (source.title or "") not in known_prior_titles]
    if unknown:
        raise ValueError(f"Refusing to prune {len(unknown)} unrecognized live source(s)")
    return extras


def validate_exact_notebook_scope(threads: list[dict[str, Any]], sources: list[Any]) -> None:
    expected = [part.get("sourceId") for thread in threads for part in thread.get("parts") or []]
    if any(not source_id for source_id in expected):
        raise ValueError("Expected source set contains an unlinked projected part")
    expected_set = set(expected)
    if len(expected_set) != len(expected):
        raise ValueError("Expected source set contains duplicate IDs")
    live_ids = {source.id for source in sources}
    missing = expected_set - live_ids
    extra = live_ids - expected_set
    if missing or extra:
        raise ValueError(f"Notebook source-set mismatch: missing={len(missing)} extra={len(extra)}")


def source_index(sources) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    by_id = {source.id: source for source in sources}
    by_title: dict[str, list[Any]] = {}
    for source in sources:
        by_title.setdefault(source.title or "", []).append(source)
    return by_id, by_title


def planned_new_sources(threads: list[dict[str, Any]], by_title: dict[str, list[Any]]) -> int:
    total = 0
    for thread in threads:
        for part in thread["parts"]:
            source_id = part.get("sourceId")
            if source_id:
                continue
            exact = by_title.get(part["title"], [])
            if len(exact) == 0:
                total += 1
            elif len(exact) > 1:
                raise ValueError(f"Duplicate live sources have title {part['title']!r}")
    return total


def planned_source_peak(threads: list[dict[str, Any]], sources: list[Any], swap_old: bool) -> dict[str, int]:
    live_by_id = {source.id: source.title or "" for source in sources}
    live_title_counts: dict[str, int] = {}
    for title in live_by_id.values():
        live_title_counts[title] = live_title_counts.get(title, 0) + 1
    current = len(live_by_id)
    peak = current
    planned_new = 0
    synthetic = 0
    for thread in threads:
        expected_ids = {part.get("sourceId") for part in thread.get("parts") or [] if part.get("sourceId") in live_by_id}
        for part in thread.get("parts") or []:
            source_id = part.get("sourceId")
            title = part.get("title") or ""
            if source_id in live_by_id or live_title_counts.get(title, 0) == 1:
                continue
            if live_title_counts.get(title, 0) > 1:
                raise ValueError(f"Duplicate live sources have title {title!r}")
            synthetic += 1
            fake_id = f"__planned_{synthetic}"
            live_by_id[fake_id] = title
            live_title_counts[title] = 1
            expected_ids.add(fake_id)
            current += 1
            planned_new += 1
        peak = max(peak, current)
        if not swap_old:
            continue
        for old in thread.get("previousSources") or []:
            old_id = old.get("sourceId")
            if not old_id or old_id in expected_ids or old_id not in live_by_id:
                continue
            if live_by_id[old_id] != (old.get("title") or ""):
                continue
            old_title = live_by_id.pop(old_id)
            live_title_counts[old_title] -= 1
            if live_title_counts[old_title] == 0:
                del live_title_counts[old_title]
            current -= 1
    return {"existing": len(sources), "plannedNew": planned_new, "projectedPeak": peak, "projectedFinal": current}


def ensure_source_capacity(existing: int, planned_new: int, limit: int) -> None:
    if existing < 0 or planned_new < 0 or limit < 1:
        raise ValueError("Invalid source-cap values")
    if existing + planned_new > limit:
        raise ValueError(f"Source cap would be exceeded: existing={existing} new={planned_new} limit={limit}")


def provider_title_equivalent(expected: str, actual: str, required_lineage: str | None = None) -> bool:
    if expected == actual:
        return True
    shorter, longer = (expected, actual) if len(expected) < len(actual) else (actual, expected)
    if len(longer) - len(shorter) != 1 or not longer.startswith(shorter):
        return False
    return not required_lineage or required_lineage in shorter


def validate_thread_lineage(thread: dict[str, Any], by_id: dict[str, Any]) -> None:
    thread_id = thread["threadId"]
    for part in thread["parts"]:
        source_id = part.get("sourceId")
        if not source_id or source_id not in by_id:
            raise ValueError(f"Missing live source for {thread_id}: {part['title']}")
        if not provider_title_equivalent(part["title"], by_id[source_id].title or "", thread_id):
            raise ValueError(f"Source title drift for {thread_id}: {source_id}")


def thread_is_current(thread: dict[str, Any], by_id: dict[str, Any]) -> bool:
    if thread.get("uploadStatus") not in {"ready", "ready-old-retained"} or thread.get("uploadRevision") != thread.get("revision"):
        return False
    if thread.get("previousSources") and thread.get("uploadStatus") != "ready-old-retained":
        return False
    try:
        validate_thread_lineage(thread, by_id)
    except ValueError:
        return False
    return True


async def sync_thread(
    client: NotebookLMClient,
    notebook_id: str,
    thread: dict[str, Any],
    state: dict[str, Any],
    state_path: Path,
    by_id: dict[str, Any],
    by_title: dict[str, list[Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    thread_id = thread["threadId"]
    uploaded: list[str] = []
    reused: list[str] = []
    for part in thread["parts"]:
        source_id = part.get("sourceId")
        if source_id and source_id in by_id:
            live = by_id[source_id]
            if not provider_title_equivalent(part["title"], live.title or "", thread_id):
                raise ValueError(f"Source title drift for {thread_id}: {source_id}")
            part["status"] = "ready"
            reused.append(source_id)
            continue
        exact = by_title.get(part["title"], [])
        if len(exact) > 1:
            raise ValueError(f"Duplicate live sources have title {part['title']!r}")
        if len(exact) == 1:
            source = exact[0]
            part["sourceId"] = source.id
            part["status"] = "ready"
            by_id[source.id] = source
            reused.append(source.id)
            atomic_json(state_path, state)
            continue
        if args.validate_only:
            raise ValueError(f"Missing live source for {thread_id}: {part['title']}")
        if args.dry_run:
            continue
        source = await client.sources.add_file(
            notebook_id,
            Path(part["file"]),
            mime_type="text/markdown",
            wait=True,
            wait_timeout=args.wait_timeout,
            title=part["title"],
        )
        part["sourceId"] = source.id
        part["status"] = "ready"
        by_id[source.id] = source
        by_title.setdefault(source.title or part["title"], []).append(source)
        uploaded.append(source.id)
        atomic_json(state_path, state)

    if args.dry_run:
        return {"threadId": thread_id, "action": "would-sync", "parts": len(thread["parts"])}

    expected_ids = [part["sourceId"] for part in thread["parts"]]
    refreshed = await client.sources.list(notebook_id, strict=True)
    refreshed_by_id, _ = source_index(refreshed)
    missing = [source_id for source_id in expected_ids if source_id not in refreshed_by_id]
    if missing:
        raise ValueError(f"Post-upload source verification failed for {thread_id}: {len(missing)} missing")

    deleted: list[str] = []
    retained_old: list[str] = []
    old_sources = thread.get("previousSources") or []
    if old_sources and args.swap_old:
        for old in old_sources:
            old_id = old.get("sourceId")
            if not old_id or old_id in expected_ids:
                continue
            live = refreshed_by_id.get(old_id)
            if live is None:
                continue
            if not provider_title_equivalent(old.get("title") or "", live.title or ""):
                raise ValueError(f"Refusing lineage-mismatched deletion for {thread_id}: {old_id}")
            await client.sources.delete(notebook_id, old_id)
            deleted.append(old_id)
        thread["previousSources"] = []
    elif old_sources:
        retained_old = [old.get("sourceId") for old in old_sources if old.get("sourceId")]

    thread["notebookId"] = notebook_id
    thread["lastUploadedAt"] = now_iso()
    thread["uploadRevision"] = thread.get("revision")
    thread["uploadStatus"] = "ready" if not retained_old else "ready-old-retained"
    thread.pop("uploadError", None)
    atomic_json(state_path, state)
    return {
        "threadId": thread_id,
        "action": "synced",
        "uploaded": len(uploaded),
        "reused": len(reused),
        "deletedOld": len(deleted),
        "retainedOld": len(retained_old),
    }


async def main() -> int:
    args = parse_args()
    state_path = args.state.resolve()
    state = read_json(state_path)
    threads = select_threads(validate_state(state), args)
    if not threads:
        raise ValueError("No projected threads matched the selection")
    validate_unique_current_lineage(threads)

    report: dict[str, Any] = {
        "startedAt": now_iso(),
        "profile": args.profile,
        "state": str(state_path),
        "policyVersion": state.get("policyVersion"),
        "dryRun": args.dry_run,
        "validateOnly": args.validate_only,
        "swapOld": args.swap_old,
        "selectedThreads": len(threads),
        "results": [],
    }
    async with NotebookLMClient.from_storage(profile=args.profile, max_concurrent_uploads=2) as client:
        notebook, would_create = await resolve_notebook(client, args)
        report["wouldCreateNotebook"] = would_create
        if notebook is None:
            report["notebookTitle"] = args.notebook_title
            report["plannedParts"] = sum(len(thread["parts"]) for thread in threads)
            print(json.dumps(report, indent=2))
            return 0

        report["notebookId"] = notebook.id
        report["notebookTitle"] = notebook.title
        sources = await client.sources.list(notebook.id, strict=True)
        pruned_orphans = []
        if args.prune_known_orphans:
            if args.dry_run or args.validate_only:
                raise ValueError("--prune-known-orphans requires a live sync run")
            pruned_orphans = known_orphans(threads, sources)
            for source in pruned_orphans:
                await client.sources.delete(notebook.id, source.id)
            sources = await client.sources.list(notebook.id, strict=True)
        by_id, by_title = source_index(sources)
        limits = await client.settings.get_account_limits()
        source_plan = planned_source_peak(threads, sources, args.swap_old)
        if source_plan["projectedPeak"] > limits.source_limit:
            raise ValueError(f"Source cap would be exceeded: peak={source_plan['projectedPeak']} limit={limits.source_limit}")
        report["sourceGate"] = {
            **source_plan,
            "limit": limits.source_limit,
            "prunedKnownOrphans": len(pruned_orphans),
        }
        if args.dry_run:
            report["results"] = [
                {"threadId": thread["threadId"], "action": "would-sync", "parts": len(thread["parts"])}
                for thread in threads
            ]
        elif args.validate_only:
            for thread in threads:
                if thread.get("notebookId") and thread.get("notebookId") != notebook.id:
                    raise ValueError(f"Thread {thread['threadId']} is linked to a different notebook")
                if thread.get("uploadRevision") != thread.get("revision"):
                    raise ValueError(f"Thread {thread['threadId']} upload revision is stale")
                if thread.get("uploadStatus") not in {"ready", "ready-old-retained"}:
                    raise ValueError(f"Thread {thread['threadId']} is not in a ready upload state")
                validate_thread_lineage(thread, by_id)
                report["results"].append({"threadId": thread["threadId"], "action": "validated", "parts": len(thread["parts"])})
            validate_exact_notebook_scope(threads, sources)
        else:
            state["notebookId"] = notebook.id
            state["notebookTitle"] = notebook.title
            atomic_json(state_path, state)
            for thread in threads:
                if thread_is_current(thread, by_id):
                    report["results"].append({"threadId": thread["threadId"], "action": "unchanged", "parts": len(thread["parts"])})
                    continue
                try:
                    result = await sync_thread(client, notebook.id, thread, state, state_path, by_id, by_title, args)
                except Exception as error:
                    thread["uploadStatus"] = "error"
                    thread["uploadError"] = f"{type(error).__name__}: {error}"
                    atomic_json(state_path, state)
                    report["results"].append({"threadId": thread["threadId"], "action": "error", "error": str(error)})
                    break
                report["results"].append(result)

        report["completedAt"] = now_iso()
        report["errors"] = sum(1 for item in report["results"] if item["action"] == "error")
        runs_dir = state_path.parent / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        report_path = runs_dir / f"upload-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{os.getpid()}.json"
        atomic_json(report_path, report)
        print(json.dumps({
            "notebookId": notebook.id,
            "notebookTitle": notebook.title,
            "selectedThreads": len(threads),
            "sourceGate": report["sourceGate"],
            "synced": sum(1 for item in report["results"] if item["action"] == "synced"),
            "unchanged": sum(1 for item in report["results"] if item["action"] == "unchanged"),
            "validated": sum(1 for item in report["results"] if item["action"] == "validated"),
            "errors": report["errors"],
            "report": str(report_path),
        }, indent=2))
        return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
