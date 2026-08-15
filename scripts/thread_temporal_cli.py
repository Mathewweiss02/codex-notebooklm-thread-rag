#!/usr/bin/env python3
"""Unified local temporal CLI.

This is the primary exact-time surface.  It composes the Node ICU resolver,
the SQLite index, and the evidence-only context packer.  NotebookLM is not
needed for any command in this file.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from thread_temporal_context import TemporalContextError, build_context  # noqa: E402
from thread_temporal_index import TemporalIndexError, query_events, query_thread_ids_by_project  # noqa: E402


CONTRACT = "temporal-cli-v1"
TOKEN_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]*")


class TemporalCliError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def add_period_args(parser: argparse.ArgumentParser, expression_default: str | None = None) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--expression", "-e", default=expression_default)
    group.add_argument("--start")
    parser.add_argument("--end")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="thread-temporal",
        description="Exact local temporal memory over the canonical Codex event index.",
    )
    parser.add_argument("--node", default="node", help="Node.js executable used for ICU timezone resolution")
    parser.add_argument("--human", action="store_true", help="Print a concise human summary instead of JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    when = subparsers.add_parser("when", help="Resolve a period without reading the index")
    add_period_args(when)
    when.add_argument("--timezone", "--tz")
    when.add_argument("--now")
    when.add_argument("--week-start", choices=["monday", "sunday"], default="monday")

    for name, help_text in (
        ("recap", "Build a local evidence recap for a period"),
        ("context", "Build a local hierarchical evidence pack"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--db", required=True, type=Path)
        add_period_args(command)
        command.add_argument("--timezone", "--tz")
        command.add_argument("--now")
        command.add_argument("--week-start", choices=["monday", "sunday"], default="monday")
        command.add_argument("--mode", choices=["brief", "standard", "deep"], default="standard")
        command.add_argument("--max-messages", type=int)
        command.add_argument("--max-chars", type=int)
        command.add_argument("--thread", action="append", dest="threads")
        command.add_argument("--project", help="Exact workspace label or hash to include")
        command.add_argument("--segment", dest="drill_down")

    find = subparsers.add_parser("find", help="Find exact local lexical matches inside a period")
    find.add_argument("--db", required=True, type=Path)
    add_period_args(find, expression_default="today")
    find.add_argument("--timezone", "--tz")
    find.add_argument("--now")
    find.add_argument("--week-start", choices=["monday", "sunday"], default="monday")
    find.add_argument("--query", "-q", required=True)
    find.add_argument("--limit", type=int, default=20)
    find.add_argument("--thread", action="append", dest="threads")
    find.add_argument("--project", help="Exact workspace label or hash to include")

    compare = subparsers.add_parser("compare", help="Compare two resolved periods without mixing their evidence")
    compare.add_argument("--db", required=True, type=Path)
    compare.add_argument("--left", required=True)
    compare.add_argument("--right", required=True)
    compare.add_argument("--timezone", "--tz")
    compare.add_argument("--now")
    compare.add_argument("--week-start", choices=["monday", "sunday"], default="monday")
    compare.add_argument("--thread", action="append", dest="threads")
    compare.add_argument("--project", help="Exact workspace label or hash to include")
    compare.add_argument("--sample-limit", type=int, default=20)
    return parser.parse_args(argv)


def resolver_args(args: argparse.Namespace, expression: str | None = None, start: str | None = None, end: str | None = None) -> list[str]:
    if expression:
        values = ["--expression", expression]
    elif start and end:
        values = ["--start", start, "--end", end]
    else:
        raise TemporalCliError("INVALID_TIME_RANGE", "provide --expression or both --start and --end")
    if getattr(args, "timezone", None):
        values.extend(["--timezone", args.timezone])
    if getattr(args, "now", None):
        values.extend(["--now", args.now])
    if getattr(args, "week_start", None):
        values.extend(["--week-start", args.week_start])
    return values


def resolve_period(args: argparse.Namespace, expression: str | None = None, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    selected_expression = expression if expression is not None else getattr(args, "expression", None)
    selected_start = start if start is not None else getattr(args, "start", None)
    selected_end = end if end is not None else getattr(args, "end", None)
    if selected_start and not selected_end:
        raise TemporalCliError("INVALID_TIME_RANGE", "--start requires --end")
    command = [args.node, str(SCRIPT_DIR / "thread_temporal_resolve.mjs"), *resolver_args(args, selected_expression, selected_start, selected_end)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
    except FileNotFoundError as exc:
        raise TemporalCliError("TIMEZONE_RUNTIME_UNAVAILABLE", f"Node runtime not found: {args.node}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TemporalCliError("TIMEZONE_RUNTIME_TIMEOUT", "period resolution exceeded 30 seconds") from exc
    output = completed.stdout.strip() or completed.stderr.strip()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise TemporalCliError("RESOLVER_MALFORMED", "temporal resolver returned malformed JSON") from exc
    if completed.returncode != 0 or payload.get("status") == "error":
        raise TemporalCliError(str(payload.get("code") or "INVALID_TIME_RANGE"), str(payload.get("message") or "temporal resolver failed"))
    required = ("startUtc", "endUtc", "timezone", "boundary")
    if any(key not in payload for key in required):
        raise TemporalCliError("RESOLVER_CONTRACT_MISMATCH", "temporal resolver omitted required range fields")
    return payload


def local_context(args: argparse.Namespace, period: dict[str, Any]) -> dict[str, Any]:
    return build_context(
        args.db.resolve(),
        period["startUtc"],
        period["endUtc"],
        period["timezone"],
        mode=getattr(args, "mode", "standard"),
        max_messages=getattr(args, "max_messages", None),
        max_chars=getattr(args, "max_chars", None),
        thread_ids=getattr(args, "threads", None),
        project=getattr(args, "project", None),
        drill_down=getattr(args, "drill_down", None),
        node_path=args.node,
        range_metadata=period,
    )


def lexical_find(args: argparse.Namespace, period: dict[str, Any]) -> dict[str, Any]:
    if args.limit < 1:
        raise TemporalCliError("INVALID_LIMIT", "--limit must be positive")
    terms = [term.lower() for term in TOKEN_RE.findall(args.query)]
    if not terms:
        raise TemporalCliError("INVALID_QUERY", "query must contain at least one alphanumeric term")
    thread_ids = args.threads
    if args.project:
        project_ids = query_thread_ids_by_project(args.db.resolve(), args.project)
        thread_ids = [thread_id for thread_id in (args.threads or project_ids) if thread_id in set(project_ids)]
    events = query_events(args.db.resolve(), period["startUtc"], period["endUtc"], thread_ids)
    phrase = " ".join(terms)
    matches = []
    for event in events:
        text = str(event["text"])
        normalized = " ".join(TOKEN_RE.findall(text.lower()))
        present = sum(term in normalized.split() for term in terms)
        if not present:
            continue
        score = present / len(set(terms))
        if phrase and phrase in normalized:
            score += 1.0
        matches.append({
            "score": round(score, 6),
            "eventId": event["eventId"],
            "threadId": event["threadId"],
            "role": event["role"],
            "timestampUtc": event["timestampUtc"],
            "text": event["text"],
            "textDigest": event["textDigest"],
            "sourceRef": event["sourceRef"],
        })
    matches.sort(key=lambda item: (-item["score"], item["timestampUtc"], item["threadId"], item["eventId"]))
    return {
        "contractVersion": "temporal-find-v1",
        "status": "ok" if matches else "empty",
        "resolvedRange": period,
        "query": {"termCount": len(set(terms)), "terms": sorted(set(terms))},
        "coverage": {"canonicalEventCount": len(events), "matchedEventCount": len(matches), "returnedEventCount": min(len(matches), args.limit), "outOfWindowEventCount": 0},
        "matches": matches[: args.limit],
    }


def compare_periods(args: argparse.Namespace) -> dict[str, Any]:
    left_period = resolve_period(args, expression=args.left)
    right_period = resolve_period(args, expression=args.right)
    thread_ids = args.threads
    if args.project:
        project_ids = query_thread_ids_by_project(args.db.resolve(), args.project)
        thread_ids = [thread_id for thread_id in (args.threads or project_ids) if thread_id in set(project_ids)]
    left_events = query_events(args.db.resolve(), left_period["startUtc"], left_period["endUtc"], thread_ids)
    right_events = query_events(args.db.resolve(), right_period["startUtc"], right_period["endUtc"], thread_ids)
    left_ids = {event["eventId"] for event in left_events}
    right_ids = {event["eventId"] for event in right_events}
    limit = max(1, args.sample_limit)
    return {
        "contractVersion": "temporal-compare-v1",
        "status": "ok",
        "left": {"resolvedRange": left_period, "canonicalEventCount": len(left_events)},
        "right": {"resolvedRange": right_period, "canonicalEventCount": len(right_events)},
        "delta": {
            "leftOnlyCount": len(left_ids - right_ids),
            "rightOnlyCount": len(right_ids - left_ids),
            "sharedCount": len(left_ids & right_ids),
            "leftOnlySample": sorted(left_ids - right_ids)[:limit],
            "rightOnlySample": sorted(right_ids - left_ids)[:limit],
            "sharedSample": sorted(left_ids & right_ids)[:limit],
        },
        "projectFilter": {"requested": args.project, "matchMode": "workspace-label-or-hash" if args.project else None},
        "evidencePolicy": "periods remain separately resolved; IDs are compared without chronology mixing",
    }


def human_summary(command: str, result: dict[str, Any]) -> str:
    if command == "when":
        return f"{result.get('requestedExpression', 'range')}: {result.get('startUtc')} <= t < {result.get('endUtc')} ({result.get('timezone')})"
    if command == "find":
        coverage = result.get("coverage", {})
        return f"{result.get('status')}: {coverage.get('matchedEventCount', 0)} matches in {coverage.get('canonicalEventCount', 0)} canonical events"
    if command == "compare":
        delta = result.get("delta", {})
        return f"left-only {delta.get('leftOnlyCount', 0)}, right-only {delta.get('rightOnlyCount', 0)}, shared {delta.get('sharedCount', 0)}"
    coverage = result.get("coverage", {})
    return f"{result.get('status')}: {coverage.get('includedEventCount', 0)}/{coverage.get('canonicalEventCount', 0)} events included across {coverage.get('segmentCount', 0)} segments"


def execute(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "when":
        return resolve_period(args)
    if args.command in {"recap", "context"}:
        period = resolve_period(args)
        return local_context(args, period)
    if args.command == "find":
        period = resolve_period(args)
        return lexical_find(args, period)
    if args.command == "compare":
        return compare_periods(args)
    raise TemporalCliError("USAGE", f"unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = parse_args(argv or sys.argv[1:])
    try:
        result = execute(args)
        wrapped = {"contractVersion": CONTRACT, "command": args.command, "result": result}
        if args.human:
            print(human_summary(args.command, result))
        else:
            print(json.dumps(wrapped, indent=2, ensure_ascii=False))
        return 0
    except (TemporalCliError, TemporalContextError, TemporalIndexError) as exc:
        payload = {"contractVersion": CONTRACT, "command": args.command, "status": "error", "code": getattr(exc, "code", "TEMPORAL_CLI_ERROR"), "message": str(exc)}
        if args.human:
            print(f"error [{payload['code']}]: {payload['message']}")
        else:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
