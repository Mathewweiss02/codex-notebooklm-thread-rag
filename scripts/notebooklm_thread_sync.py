#!/usr/bin/env python3
"""Upload validated Codex thread projections to NotebookLM with guarded revision swaps."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from notebooklm import NotebookLMClient
from redaction_contract import summarize_error


REQUIRED_POLICY = "visible-messages-secrets-redacted-v4"


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
    os.replace(temporary, path)


def validate_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    policy = state.get("policyVersion")
    if policy != REQUIRED_POLICY:
        raise ValueError(f"Refusing policy {policy!r}; required {REQUIRED_POLICY!r}")
    threads = state.get("threads")
    if not isinstance(threads, dict) or not threads:
        raise ValueError("State contains no projected threads")
    validated: list[dict[str, Any]] = []
    title_owners: dict[str, str] = {}
    source_owners: dict[str, str] = {}
    for thread_id, thread in threads.items():
        if thread.get("policyVersion") != REQUIRED_POLICY:
            raise ValueError(f"Thread {thread_id} has the wrong projection policy")
        if int((thread.get("stats") or {}).get("overflowVisibleLines") or 0) != 0:
            raise ValueError(f"Thread {thread_id} skipped an oversized visible message")
        parts = thread.get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError(f"Thread {thread_id} has no source parts")
        for part in parts:
            part_key = f"{thread_id}:p{part.get('part')}"
            file_path = Path(part.get("file") or "")
            if not file_path.is_file():
                raise ValueError(f"Missing projected part for {thread_id}: {file_path}")
            if file_path.stat().st_size != int(part.get("bytes") or -1):
                raise ValueError(f"Projected part size drift for {thread_id}: {file_path}")
            title = str(part.get("title") or "")
            if not title:
                raise ValueError(f"Projected part lacks a source title for {thread_id}")
            prior_title_owner = title_owners.setdefault(title, part_key)
            if prior_title_owner != part_key:
                raise ValueError(f"Duplicate projected source title across parts: {title!r}")
            source_id = str(part.get("sourceId") or "")
            if source_id:
                prior_source_owner = source_owners.setdefault(source_id, part_key)
                if prior_source_owner != part_key:
                    raise ValueError("One live source id is assigned to multiple projected parts")
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
    parser.add_argument("--reject-untracked-sources", action="store_true", help="Fail when the dedicated notebook contains a source outside known state lineage")
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


def source_index(sources) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    by_id: dict[str, Any] = {}
    by_title: dict[str, list[Any]] = {}
    for source in sources:
        if source.id in by_id:
            raise ValueError(f"Duplicate live source id: {source.id}")
        by_id[source.id] = source
        by_title.setdefault(source.title or "", []).append(source)
    return by_id, by_title


def known_lineage_source_ids(state: dict[str, Any]) -> set[str]:
    source_ids: set[str] = set()
    for thread in (state.get("threads") or {}).values():
        for part in list(thread.get("parts") or []) + list(thread.get("previousSources") or []):
            source_id = str(part.get("sourceId") or "")
            if source_id:
                source_ids.add(source_id)
    return source_ids


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


def ensure_source_capacity(existing: int, planned_new: int, limit: int) -> None:
    if existing < 0 or planned_new < 0 or limit < 1:
        raise ValueError("Invalid source-cap values")
    if existing + planned_new > limit:
        raise ValueError(f"Source cap would be exceeded: existing={existing} new={planned_new} limit={limit}")


def validate_thread_lineage(thread: dict[str, Any], by_id: dict[str, Any]) -> None:
    thread_id = thread["threadId"]
    for part in thread["parts"]:
        source_id = part.get("sourceId")
        if not source_id or source_id not in by_id:
            raise ValueError(f"Missing live source for {thread_id}: {part['title']}")
        if (by_id[source_id].title or "") != part["title"]:
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
            if (live.title or "") != part["title"]:
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
            if (live.title or "") != (old.get("title") or ""):
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
        by_id, by_title = source_index(sources)
        known_ids = known_lineage_source_ids(state)
        untracked_ids = set(by_id) - known_ids
        report["sourceReconcile"] = {
            "live": len(by_id),
            "knownLineage": len(set(by_id) & known_ids),
            "untracked": len(untracked_ids),
        }
        if args.reject_untracked_sources and untracked_ids:
            raise ValueError(f"Dedicated retrieval notebook contains {len(untracked_ids)} untracked sources")
        limits = await client.settings.get_account_limits()
        new_count = planned_new_sources(threads, by_title)
        ensure_source_capacity(len(sources), new_count, limits.source_limit)
        report["sourceGate"] = {
            "existing": len(sources),
            "plannedNew": new_count,
            "limit": limits.source_limit,
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
                    thread["uploadError"] = summarize_error(error)
                    atomic_json(state_path, state)
                    report["results"].append({"threadId": thread["threadId"], "action": "error", "error": summarize_error(error)})
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
