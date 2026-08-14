#!/usr/bin/env python3
"""Map selected local thread lineage to current ready retrieval sources.

This is a read-only boundary.  It never creates, deletes, renames, or resets a
NotebookLM source or conversation.  Remote source listing is optional and
read-only; local projection state is still required and is checked first.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


CONTRACT = "temporal-source-map-v1"
POLICY = "visible-messages-secrets-redacted-v4"
READY_UPLOAD_STATUSES = {"ready", "ready-old-retained"}
BAD_REMOTE_STATUSES = {"error", "failed", "processing", "uploading", "pending"}


class SourceMapError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise SourceMapError("STATE_MISSING", f"required local state is missing: {path.name}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceMapError("STATE_INVALID", f"local state is unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise SourceMapError("STATE_INVALID", f"local state is not an object: {path.name}")
    return value


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise SourceMapError("SOURCE_DRIFT", f"projected source file is unreadable: {path.name}") from exc
    return digest.hexdigest()


def discover_config(explicit: Path | None, registry_path: Path | None, device: str | None) -> Path:
    if explicit:
        return explicit.resolve()
    root = Path(os.environ.get("USERPROFILE") or Path.home())
    registry = registry_path.resolve() if registry_path else root / ".codex" / "thread-rag" / "registry.json"
    data = read_json(registry)
    candidates = []
    for item in data.get("Configs") or []:
        if str(item.get("NotebookRole") or "") != "retrieval":
            continue
        if device and str(item.get("Device") or "") != device:
            continue
        config_path = item.get("ConfigPath")
        if config_path:
            candidates.append(Path(str(config_path)).resolve())
    if not candidates:
        raise SourceMapError("CONFIG_NOT_FOUND", "no registered retrieval config matches the requested device")
    if len(candidates) != 1:
        raise SourceMapError("CONFIG_AMBIGUOUS", "select one retrieval config with --config or --device")
    return candidates[0]


def context_thread_ids(path: Path) -> set[str]:
    data = read_json(path)
    root = data.get("result") if isinstance(data.get("result"), dict) else data
    ids: set[str] = set()
    selection = root.get("selection") if isinstance(root, dict) else None
    for value in (selection or {}).get("threadIds") or []:
        if value:
            ids.add(str(value))
    for message in (root.get("messages") or []) if isinstance(root, dict) else []:
        if isinstance(message, dict) and message.get("threadId"):
            ids.add(str(message["threadId"]))
    if not ids:
        raise SourceMapError("THREAD_SCOPE_REQUIRED", "context pack contains no selected thread IDs")
    return ids


def selected_thread_ids(thread_ids: list[str] | None, context_pack: Path | None) -> list[str]:
    values = {str(value) for value in (thread_ids or []) if str(value)}
    if context_pack:
        values.update(context_thread_ids(context_pack))
    if not values:
        raise SourceMapError("THREAD_SCOPE_REQUIRED", "provide --thread or --context-pack")
    return sorted(values)


def validate_state(config_path: Path, wanted_ids: list[str]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    config = read_json(config_path)
    if str(config.get("NotebookRole") or "") != "retrieval":
        raise SourceMapError("NOTEBOOK_ROLE_UNSAFE", "automated source mapping requires NotebookRole=retrieval")
    if config.get("DisposableSearchChat") is not True:
        raise SourceMapError("CONVERSATION_UNSAFE", "retrieval source mapping requires DisposableSearchChat=true")
    projection_value = str(config.get("ProjectionRoot") or "").strip()
    if not projection_value:
        raise SourceMapError("STATE_MISSING", "retrieval config has no ProjectionRoot")
    projection_root = Path(projection_value).expanduser()
    state = read_json(projection_root / "state.json")
    if state.get("policyVersion") != POLICY:
        raise SourceMapError("POLICY_MISMATCH", "projection state uses an unsupported redaction policy")
    if config.get("NotebookId") and state.get("notebookId") and config.get("NotebookId") != state.get("notebookId"):
        raise SourceMapError("STATE_INCONSISTENT", "config and projection state refer to different notebooks")
    threads = state.get("threads") or {}
    if not isinstance(threads, dict):
        raise SourceMapError("STATE_INVALID", "projection state threads is not an object")

    all_source_owners: dict[str, str] = {}
    all_titles: dict[str, str] = {}
    for thread_id, thread in threads.items():
        for part in thread.get("parts") or []:
            source_id = str(part.get("sourceId") or "")
            title = str(part.get("title") or "")
            if source_id:
                prior = all_source_owners.setdefault(source_id, str(thread_id))
                if prior != str(thread_id):
                    raise SourceMapError("STATE_INCONSISTENT", "one source ID is owned by multiple threads")
            if title:
                prior = all_titles.setdefault(title, f"{thread_id}:p{part.get('part')}")
                if prior != f"{thread_id}:p{part.get('part')}" and source_id:
                    raise SourceMapError("STATE_INCONSISTENT", "current projected source titles are not unique")

    entries: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for thread_id in wanted_ids:
        thread = threads.get(thread_id)
        if not isinstance(thread, dict):
            problems.append({"threadId": thread_id, "code": "THREAD_NOT_ENROLLED", "message": "thread is absent from retrieval projection state"})
            continue
        if thread.get("uploadRevision") != thread.get("revision") or thread.get("uploadStatus") not in READY_UPLOAD_STATUSES:
            problems.append({"threadId": thread_id, "code": "SOURCE_MAPPING_STALE", "message": "thread upload is not at its current ready revision"})
            continue
        parts = thread.get("parts") or []
        if not parts:
            problems.append({"threadId": thread_id, "code": "SOURCE_MAPPING_STALE", "message": "thread has no current source parts"})
            continue
        for part in parts:
            part_number = part.get("part")
            source_id = str(part.get("sourceId") or "")
            title = str(part.get("title") or "")
            local_file = Path(str(part.get("file") or ""))
            if part.get("status") != "ready" or not source_id or not title:
                problems.append({"threadId": thread_id, "part": part_number, "code": "SOURCE_MAPPING_STALE", "message": "current source part is not ready and identified"})
                continue
            if not local_file.is_file():
                problems.append({"threadId": thread_id, "part": part_number, "code": "SOURCE_DRIFT", "message": "projected source file is missing"})
                continue
            observed_digest = file_digest(local_file)
            expected_digest = str(part.get("sha256") or "")
            if expected_digest and observed_digest != expected_digest:
                problems.append({"threadId": thread_id, "part": part_number, "code": "SOURCE_DRIFT", "message": "projected source digest changed"})
                continue
            entries.append({
                "threadId": thread_id,
                "title": title,
                "part": part_number,
                "totalParts": part.get("totalParts"),
                "sourceId": source_id,
                "revision": thread.get("revision"),
                "sourceSha256": expected_digest or observed_digest,
            })
    return config, state, entries + problems


def live_verify(
    config: dict[str, Any],
    entries: list[dict[str, Any]],
    notebooklm: str,
    timeout: int,
    allowed_lineage_ids: set[str] | None = None,
) -> dict[str, Any]:
    wanted = {str(entry["sourceId"]): str(entry["title"]) for entry in entries if entry.get("sourceId")}
    allowed_ids = set(wanted) | set(allowed_lineage_ids or set())
    command = [notebooklm, "--quiet", "--profile", str(config.get("Profile") or ""), "source", "list", "--notebook", str(config.get("NotebookId") or ""), "--json"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"attempted": True, "status": "unavailable", "code": "REMOTE_SOURCE_LIST_UNAVAILABLE", "matched": 0, "missing": len(wanted), "mismatched": 0}
    if completed.returncode != 0:
        return {"attempted": True, "status": "unavailable", "code": "REMOTE_SOURCE_LIST_UNAVAILABLE", "matched": 0, "missing": len(wanted), "mismatched": 0}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"attempted": True, "status": "unavailable", "code": "REMOTE_SOURCE_LIST_INVALID", "matched": 0, "missing": len(wanted), "mismatched": 0}
    rows = payload.get("sources") if isinstance(payload, dict) else payload
    rows = rows if isinstance(rows, list) else []
    live: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("id") or row.get("sourceId") or "")
        if source_id:
            live[source_id] = row
    missing = 0
    mismatched = 0
    bad_status = 0
    for source_id, title in wanted.items():
        row = live.get(source_id)
        if row is None:
            missing += 1
            continue
        live_title = str(row.get("title") or row.get("name") or "")
        if live_title and live_title != title:
            mismatched += 1
        status = str(row.get("status") or row.get("state") or "").lower()
        if status in BAD_REMOTE_STATUSES:
            bad_status += 1
    untracked = len(set(live) - allowed_ids)
    status = "ok" if not (missing or mismatched or bad_status or untracked) else "degraded"
    return {
        "attempted": True,
        "status": status,
        "matched": len(wanted) - missing,
        "missing": missing,
        "mismatched": mismatched,
        "badStatus": bad_status,
        "untracked": untracked,
        "allowedLineage": len(set(allowed_lineage_ids or set())),
    }


def map_sources(config_path: Path, wanted_ids: list[str], live: bool = False, notebooklm: str | None = None, timeout: int = 30) -> dict[str, Any]:
    started = time.perf_counter()
    config, state, raw_entries = validate_state(config_path.resolve(), wanted_ids)
    entries = [entry for entry in raw_entries if entry.get("sourceId")]
    problems = [entry for entry in raw_entries if not entry.get("sourceId")]
    live_result = {"attempted": False, "status": "not-run"}
    if live and not problems:
        previous_ids = {
            str(previous.get("sourceId"))
            for thread in (state.get("threads") or {}).values()
            if isinstance(thread, dict)
            for previous in (thread.get("previousSources") or [])
            if isinstance(previous, dict) and previous.get("sourceId")
        }
        live_result = live_verify(
            config,
            entries,
            notebooklm or str(config.get("NotebookLmCli") or "notebooklm"),
            timeout,
            previous_ids,
        )
        if live_result.get("status") != "ok":
            problems.append({"code": live_result.get("code") or "REMOTE_SOURCE_DRIFT", "message": "live retrieval source verification did not pass"})
    status = "ok" if not problems else "degraded"
    return {
        "contractVersion": CONTRACT,
        "status": status,
        "config": {
            "device": config.get("Device"),
            "notebookRole": config.get("NotebookRole"),
            "profile": config.get("Profile"),
            "conversationPolicy": config.get("ConversationPolicy"),
            "disposableSearchChat": config.get("DisposableSearchChat"),
            "notebookId": config.get("NotebookId"),
        },
        "selection": {"requestedThreadCount": len(wanted_ids), "requestedThreadIds": wanted_ids},
        "mapping": entries,
        "problems": problems,
        "liveVerification": live_result,
        "state": {"policyVersion": state.get("policyVersion"), "updatedAt": state.get("updatedAt"), "notebookId": state.get("notebookId")},
        "coverage": {"requestedThreadCount": len(wanted_ids), "mappedThreadCount": len({entry["threadId"] for entry in entries}), "mappedPartCount": len(entries), "problemCount": len(problems)},
        "latency": {"totalMs": round((time.perf_counter() - started) * 1000, 3)},
    }


def public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove notebook/source/thread identifiers from CLI-facing reports."""
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    problems = payload.get("problems") if isinstance(payload.get("problems"), list) else []
    safe_problems = [
        {key: value for key, value in item.items() if key in {"code", "part", "message"}}
        for item in problems
        if isinstance(item, dict)
    ]
    return {
        "contractVersion": payload.get("contractVersion"),
        "status": payload.get("status"),
        "config": {
            "device": config.get("device"),
            "notebookRole": config.get("notebookRole"),
            "profile": config.get("profile"),
            "conversationPolicy": config.get("conversationPolicy"),
            "disposableSearchChat": config.get("disposableSearchChat"),
        },
        "selection": {"requestedThreadCount": selection.get("requestedThreadCount")},
        "problems": safe_problems,
        "liveVerification": payload.get("liveVerification"),
        "state": {"policyVersion": state.get("policyVersion"), "updatedAt": state.get("updatedAt")},
        "coverage": payload.get("coverage"),
        "latency": payload.get("latency"),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Map selected threads to current ready retrieval sources without mutating NotebookLM.")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--device")
    parser.add_argument("--thread", action="append", dest="threads")
    parser.add_argument("--context-pack", type=Path)
    parser.add_argument("--all", action="store_true", dest="all_threads", help="map every current thread in the selected retrieval state")
    parser.add_argument("--live-verify", action="store_true")
    parser.add_argument("--notebooklm", help="Optional read-only NotebookLM CLI override; config value is used by default")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--strict", action="store_true", help="return nonzero when any mapping is degraded")
    parser.add_argument("--include-identifiers", action="store_true", help="include raw source/thread identifiers in this diagnostic output")
    parser.add_argument("--out", type=Path)
    return parser.parse_args(argv)


def write_output(payload: dict[str, Any], destination: Path | None) -> None:
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if destination is None:
        sys.stdout.write(serialized)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(serialized, encoding="utf-8", newline="\n")
    temporary.replace(destination)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = parse_args(argv or sys.argv[1:])
    try:
        config_path = discover_config(args.config, args.registry, args.device)
        if args.all_threads:
            config = read_json(config_path)
            projection_value = str(config.get("ProjectionRoot") or "").strip()
            if not projection_value:
                raise SourceMapError("STATE_MISSING", "retrieval config has no ProjectionRoot")
            state = read_json(Path(projection_value).expanduser() / "state.json")
            thread_map = state.get("threads") or {}
            if not isinstance(thread_map, dict) or not thread_map:
                raise SourceMapError("THREAD_SCOPE_REQUIRED", "retrieval state contains no threads")
            wanted = sorted(str(value) for value in thread_map)
        else:
            wanted = selected_thread_ids(args.threads, args.context_pack)
        payload = map_sources(config_path, wanted, args.live_verify, args.notebooklm, args.timeout)
        write_output(payload if args.include_identifiers else public_payload(payload), args.out)
        return 1 if args.strict and payload["status"] != "ok" else 0
    except SourceMapError as exc:
        payload = {"contractVersion": CONTRACT, "status": "error", "code": exc.code, "message": str(exc)}
        write_output(payload, args.out)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
