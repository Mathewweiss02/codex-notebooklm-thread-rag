#!/usr/bin/env python3
"""Build a hierarchical, provenance-preserving temporal context pack.

The SQLite index remains the local authority.  This layer only selects,
segments, budgets, and formats already-sanitized canonical events; it does not
generate factual summaries and it never uses NotebookLM state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from thread_temporal_index import TemporalIndexError, query_events, query_thread_events, timestamp_ms  # noqa: E402


CONTRACT = "temporal-context-pack-v1"
SEGMENTATION_CONTRACT = "activity-segmentation-v1"
SEGMENTATION_THRESHOLD_MINUTES = 60
SEGMENTATION_THRESHOLD_MS = SEGMENTATION_THRESHOLD_MINUTES * 60 * 1000
LOCAL_DAY_CONTRACT = "temporal-local-day-v1"
MODE_BUDGETS: dict[str, dict[str, int]] = {
    "brief": {"maxMessages": 48, "maxChars": 16_000},
    "standard": {"maxMessages": 256, "maxChars": 100_000},
    "deep": {"maxMessages": 2_000, "maxChars": 500_000},
}


class TemporalContextError(RuntimeError):
    """Expected context-packing failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def event_ms(event: dict[str, Any]) -> int:
    return timestamp_ms(str(event["timestampUtc"]))


def segment_id(thread_id: str, first_event_id: str) -> str:
    raw = "\x00".join([SEGMENTATION_CONTRACT, thread_id, first_event_id])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolved_range(start: str, end: str, timezone_name: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    if metadata:
        if metadata.get("startUtc") not in {None, start} or metadata.get("endUtc") not in {None, end}:
            raise TemporalContextError("INVALID_RANGE_METADATA", "resolver metadata does not match the requested UTC bounds")
        if metadata.get("timezone") not in {None, timezone_name}:
            raise TemporalContextError("INVALID_RANGE_METADATA", "resolver metadata timezone does not match the requested timezone")
        allowed = {
            "contractVersion", "requestedExpression", "kind", "timezone", "nowUtc", "nowLocal",
            "startUtc", "endUtc", "startLocal", "endLocal", "boundary", "durationSeconds",
            "future", "expectedActivity",
        }
        result = {key: value for key, value in metadata.items() if key in allowed}
        result.setdefault("timezone", timezone_name)
        result.setdefault("startUtc", start)
        result.setdefault("endUtc", end)
        result.setdefault("boundary", "half-open [start,end)")
        return result
    return {
        "timezone": timezone_name,
        "startUtc": start,
        "endUtc": end,
        "boundary": "half-open [start,end)",
    }


def localize_events(events: list[dict[str, Any]], timezone_name: str, node_path: str) -> dict[str, str]:
    helper = SCRIPT_DIR / "thread_temporal_localize.mjs"
    payload = json.dumps(
        [{"eventId": event["eventId"], "timestampUtc": event["timestampUtc"]} for event in events],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    try:
        completed = subprocess.run(
            [node_path, str(helper), "--timezone", timezone_name],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        raise TemporalContextError("TIMEZONE_RUNTIME_UNAVAILABLE", f"Node runtime not found: {node_path}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TemporalContextError("TIMEZONE_RUNTIME_TIMEOUT", "local-day conversion exceeded 30 seconds") from exc
    if completed.returncode != 0:
        try:
            error = json.loads(completed.stderr or "{}")
            code = str(error.get("code") or "TIMEZONE_RUNTIME_ERROR")
            message = str(error.get("message") or completed.stderr or "local-day conversion failed")
        except json.JSONDecodeError:
            code = "TIMEZONE_RUNTIME_ERROR"
            message = completed.stderr.strip() or "local-day conversion failed"
        raise TemporalContextError(code, message)
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise TemporalContextError("TIMEZONE_RUNTIME_ERROR", "local-day converter returned malformed JSON") from exc
    if result.get("contractVersion") != LOCAL_DAY_CONTRACT or result.get("timezone") != timezone_name:
        raise TemporalContextError("TIMEZONE_RUNTIME_ERROR", "local-day converter contract mismatch")
    localized = result.get("events")
    if not isinstance(localized, list) or len(localized) != len(events):
        raise TemporalContextError("TIMEZONE_RUNTIME_ERROR", "local-day converter returned incomplete output")
    mapping: dict[str, str] = {}
    for item in localized:
        event_id = str(item.get("eventId") or "")
        local_date = str(item.get("localDate") or "")
        if not event_id or not local_date or event_id in mapping:
            raise TemporalContextError("TIMEZONE_RUNTIME_ERROR", "local-day converter returned invalid event identity")
        mapping[event_id] = local_date
    expected_ids = {str(event["eventId"]) for event in events}
    if set(mapping) != expected_ids:
        raise TemporalContextError("TIMEZONE_RUNTIME_ERROR", "local-day converter event identities do not match input")
    return mapping


def build_segments(all_events: list[dict[str, Any]], selected_ids: set[str], start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    by_thread: dict[str, list[dict[str, Any]]] = {}
    for event in all_events:
        by_thread.setdefault(str(event["threadId"]), []).append(event)

    segments: list[dict[str, Any]] = []
    for thread_id, events in by_thread.items():
        ordered = sorted(events, key=lambda item: (event_ms(item), str(item["eventId"])))
        current: list[dict[str, Any]] = []
        previous_ms: int | None = None

        def flush() -> None:
            if not current:
                return
            selected = [event for event in current if str(event["eventId"]) in selected_ids]
            if not selected:
                return
            first = current[0]
            last = current[-1]
            selected_positions = [index for index, event in enumerate(current) if str(event["eventId"]) in selected_ids]
            segments.append(
                {
                    "segmentId": segment_id(thread_id, str(first["eventId"])),
                    "threadId": thread_id,
                    "firstTimestampUtc": first["timestampUtc"],
                    "lastTimestampUtc": last["timestampUtc"],
                    "firstEventId": first["eventId"],
                    "lastEventId": last["eventId"],
                    "allEvents": list(current),
                    "selectedEvents": selected,
                    "truncatedBefore": selected_positions[0] > 0,
                    "truncatedAfter": selected_positions[-1] < len(current) - 1,
                    "selectedStartMs": min(event_ms(event) for event in selected),
                    "selectedEndMs": max(event_ms(event) for event in selected),
                    "queryStartMs": start_ms,
                    "queryEndMs": end_ms,
                }
            )

        for event in ordered:
            current_ms = event_ms(event)
            if previous_ms is not None and current_ms - previous_ms > SEGMENTATION_THRESHOLD_MS:
                flush()
                current = []
            current.append(event)
            previous_ms = current_ms
        flush()

    segments.sort(key=lambda item: (item["selectedStartMs"], item["threadId"], item["firstEventId"]))
    return segments


def budget_events(
    events: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    max_messages: int,
    max_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_segment: dict[str, list[dict[str, Any]]] = {
        str(segment["segmentId"]): sorted(segment["selectedEvents"], key=lambda item: (event_ms(item), item["eventId"]))
        for segment in segments
    }
    ordered_segments = [str(segment["segmentId"]) for segment in segments]
    cursors = {segment_id_value: 0 for segment_id_value in ordered_segments}
    included: list[dict[str, Any]] = []
    omitted_messages = 0
    omitted_chars = 0
    omitted_by_message_limit = 0
    omitted_by_char_limit = 0
    total = len(events)

    while True:
        advanced = False
        for current_segment_id in ordered_segments:
            segment_events = by_segment[current_segment_id]
            cursor = cursors[current_segment_id]
            if cursor >= len(segment_events):
                continue
            advanced = True
            candidate = segment_events[cursor]
            cursors[current_segment_id] = cursor + 1
            text_length = len(str(candidate["text"]))
            if len(included) >= max_messages:
                omitted_messages += 1
                omitted_chars += text_length
                omitted_by_message_limit += 1
                continue
            if sum(len(str(item["text"])) for item in included) + text_length > max_chars:
                omitted_messages += 1
                omitted_chars += text_length
                omitted_by_char_limit += 1
                continue
            included.append(candidate)
        if not advanced:
            break

    if len(included) + omitted_messages != total:
        raise TemporalContextError("BUDGET_ACCOUNTING_MISMATCH", "context budget did not account for every selected event")
    included.sort(key=lambda item: (event_ms(item), item["threadId"], item["eventId"]))
    included_chars = sum(len(str(item["text"])) for item in included)
    return included, {
        "omittedMessages": omitted_messages,
        "omittedChars": omitted_chars,
        "omittedByMessageLimit": omitted_by_message_limit,
        "omittedByCharLimit": omitted_by_char_limit,
        "includedChars": included_chars,
    }


def output_event(event: dict[str, Any], local_dates: dict[str, str], segment_by_event: dict[str, str]) -> dict[str, Any]:
    event_id = str(event["eventId"])
    return {
        "eventId": event_id,
        "threadId": event["threadId"],
        "role": event["role"],
        "timestampUtc": event["timestampUtc"],
        "localDate": local_dates[event_id],
        "text": event["text"],
        "textDigest": event["textDigest"],
        "sourceRef": event["sourceRef"],
        "segmentId": segment_by_event[event_id],
    }


def output_segment(segment: dict[str, Any], included_ids: set[str], local_dates: dict[str, str]) -> dict[str, Any]:
    selected_events = segment["selectedEvents"]
    selected_ids = [event["eventId"] for event in selected_events]
    omitted_ids = [event_id for event_id in selected_ids if event_id not in included_ids]
    source_refs = []
    seen_refs: set[tuple[str, str, int]] = set()
    for event in selected_events:
        ref = event["sourceRef"]
        key = (ref["sourceKind"], ref["sourceFileDigest"], ref["lineNumber"])
        if key not in seen_refs:
            seen_refs.add(key)
            source_refs.append(ref)
    local_dates_present = sorted({local_dates[event_id] for event_id in selected_ids})
    return {
        "segmentId": segment["segmentId"],
        "threadId": segment["threadId"],
        "firstTimestampUtc": segment["firstTimestampUtc"],
        "lastTimestampUtc": segment["lastTimestampUtc"],
        "firstEventId": segment["firstEventId"],
        "lastEventId": segment["lastEventId"],
        "localDates": local_dates_present,
        "totalHistoryEventCount": len(segment["allEvents"]),
        "canonicalEventCount": len(selected_events),
        "includedEventCount": len(selected_ids) - len(omitted_ids),
        "omittedEventCount": len(omitted_ids),
        "selectedEventIds": selected_ids,
        "includedEventIds": [event_id for event_id in selected_ids if event_id in included_ids],
        "omittedEventIds": omitted_ids,
        "truncatedBefore": segment["truncatedBefore"],
        "truncatedAfter": segment["truncatedAfter"],
        "sourceRefs": source_refs,
        "drillDown": {"segmentId": segment["segmentId"], "scope": "activity-segment"},
    }


def output_days(events: list[dict[str, Any]], included_ids: set[str], local_dates: dict[str, str], segment_by_event: dict[str, str], segments_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by_day: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_day.setdefault(local_dates[event["eventId"]], []).append(event)
    days = []
    for local_date, day_events in sorted(by_day.items()):
        day_events.sort(key=lambda item: (event_ms(item), item["threadId"], item["eventId"]))
        segment_ids = []
        for event in day_events:
            current_segment_id = segment_by_event[event["eventId"]]
            if current_segment_id not in segment_ids:
                segment_ids.append(current_segment_id)
        segment_ids.sort(key=lambda value: (segments_by_id[value]["selectedStartMs"], segments_by_id[value]["threadId"], segments_by_id[value]["firstEventId"]))
        days.append(
            {
                "localDate": local_date,
                "canonicalEventCount": len(day_events),
                "includedEventCount": sum(event["eventId"] in included_ids for event in day_events),
                "omittedEventCount": sum(event["eventId"] not in included_ids for event in day_events),
                "segmentCount": len(segment_ids),
                "segmentIds": segment_ids,
                "eventIds": [event["eventId"] for event in day_events],
            }
        )
    return days


def empty_result(start: str, end: str, timezone_name: str, mode: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    budget = MODE_BUDGETS[mode]
    return {
        "contractVersion": CONTRACT,
        "status": "empty",
        "mode": mode,
        "selection": {"scope": "period", "threadIds": [], "segmentId": None},
        "resolvedRange": resolved_range(start, end, timezone_name, metadata),
        "policy": {"contract": SEGMENTATION_CONTRACT, "thresholdMinutes": SEGMENTATION_THRESHOLD_MINUTES, "newSegmentWhen": "timestamp gap > threshold", "localDateBoundary": "does not split", "timezoneProvider": "node-intl-icu"},
        "coverage": {
            "canonicalEventCount": 0,
            "includedEventCount": 0,
            "omittedEventCount": 0,
            "segmentCount": 0,
            "localDayCount": 0,
            "completeSelection": True,
            "outOfWindowEventCount": 0,
            "budget": budget,
            "omissionReasons": {},
        },
        "days": [],
        "segments": [],
        "messages": [],
        "drillDownHandles": [],
        "verification": {"status": "local-authoritative", "provenanceComplete": True, "claimPolicy": "evidence pack only; no generated factual summary", "outOfWindowEventCount": 0},
        "latency": {"totalMs": 0},
    }


def build_context(
    database: Path,
    start: str,
    end: str,
    timezone_name: str,
    mode: str = "standard",
    max_messages: int | None = None,
    max_chars: int | None = None,
    thread_ids: list[str] | None = None,
    drill_down: str | None = None,
    node_path: str = "node",
    range_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    if mode not in MODE_BUDGETS:
        raise TemporalContextError("INVALID_MODE", f"unsupported context mode: {mode}")
    budget = dict(MODE_BUDGETS[mode])
    if max_messages is not None:
        budget["maxMessages"] = max_messages
    if max_chars is not None:
        budget["maxChars"] = max_chars
    if budget["maxMessages"] < 1 or budget["maxChars"] < 1:
        raise TemporalContextError("BUDGET_EXCEEDED", "message and character budgets must be positive")

    start_ms = timestamp_ms(start)
    end_ms = timestamp_ms(end)
    if end_ms < start_ms:
        raise TemporalContextError("INVALID_TIME_RANGE", "end must not precede start")
    if end_ms == start_ms:
        result = empty_result(start, end, timezone_name, mode, range_metadata)
        result["coverage"]["budget"] = budget
        result["latency"]["totalMs"] = round((time.perf_counter() - started) * 1000, 3)
        return result

    selected_events = query_events(database, start, end, thread_ids)
    if not selected_events:
        result = empty_result(start, end, timezone_name, mode, range_metadata)
        result["coverage"]["budget"] = budget
        result["latency"]["totalMs"] = round((time.perf_counter() - started) * 1000, 3)
        return result

    selected_ids = {str(event["eventId"]) for event in selected_events}
    selected_threads = sorted({str(event["threadId"]) for event in selected_events})
    history = query_thread_events(database, selected_threads)
    history_ids = {str(event["eventId"]) for event in history}
    if not selected_ids.issubset(history_ids):
        raise TemporalContextError("INDEX_INCONSISTENT", "selected event is missing from thread history")

    local_dates = localize_events(selected_events, timezone_name, node_path)
    period_segments = build_segments(history, selected_ids, start_ms, end_ms)
    if not period_segments:
        raise TemporalContextError("SEGMENT_ACCOUNTING_MISMATCH", "selected events did not produce activity segments")
    segment_by_event = {
        str(event["eventId"]): str(segment["segmentId"])
        for segment in period_segments
        for event in segment["selectedEvents"]
    }
    segments_by_id = {str(segment["segmentId"]): segment for segment in period_segments}

    if drill_down:
        target = segments_by_id.get(drill_down)
        if target is None:
            raise TemporalContextError("SEGMENT_NOT_FOUND", f"activity segment does not exist in the requested period: {drill_down}")
        pack_segments = [target]
        pack_events = list(target["selectedEvents"])
        scope = "activity-segment"
    else:
        pack_segments = period_segments
        pack_events = list(selected_events)
        scope = "period"

    included_events, budget_stats = budget_events(pack_events, pack_segments, budget["maxMessages"], budget["maxChars"])
    included_ids = {str(event["eventId"]) for event in included_events}
    messages = [output_event(event, local_dates, segment_by_event) for event in included_events]
    segment_output = [output_segment(segment, included_ids, local_dates) for segment in pack_segments]
    days = output_days(pack_events, included_ids, local_dates, segment_by_event, segments_by_id)
    omission_reasons = {}
    if budget_stats["omittedByMessageLimit"]:
        omission_reasons["message-budget"] = budget_stats["omittedByMessageLimit"]
    if budget_stats["omittedByCharLimit"]:
        omission_reasons["character-budget"] = budget_stats["omittedByCharLimit"]
    period_scope_omissions = len(selected_events) - len(pack_events)
    if period_scope_omissions:
        omission_reasons["drill-down-scope"] = period_scope_omissions

    # A drill-down intentionally narrows the view; that is not a degraded
    # result. Only budget loss changes the trust status.
    status = "degraded" if budget_stats["omittedMessages"] else "ok"
    result = {
        "contractVersion": CONTRACT,
        "status": status,
        "mode": mode,
        "selection": {
            "scope": scope,
            "threadIds": selected_threads,
            "segmentId": drill_down,
            "periodCanonicalEventCount": len(selected_events),
        },
        "resolvedRange": resolved_range(start, end, timezone_name, range_metadata),
        "policy": {
            "contract": SEGMENTATION_CONTRACT,
            "thresholdMinutes": SEGMENTATION_THRESHOLD_MINUTES,
            "newSegmentWhen": "timestamp gap > threshold",
            "threadBoundary": "different thread IDs never merge",
            "localDateBoundary": "does not split",
            "timezoneProvider": "node-intl-icu",
            "ordering": ["timestampUtc", "threadId", "eventId"],
        },
        "coverage": {
            "canonicalEventCount": len(pack_events),
            "includedEventCount": len(included_events),
            "omittedEventCount": len(pack_events) - len(included_events),
            "periodCanonicalEventCount": len(selected_events),
            "periodSegmentCount": len(period_segments),
            "segmentCount": len(pack_segments),
            "localDayCount": len(days),
            "completeSelection": True,
            "outOfWindowEventCount": 0,
            "canonicalContentChars": sum(len(str(event["text"])) for event in pack_events),
            "includedContentChars": budget_stats["includedChars"],
            "omittedContentChars": budget_stats["omittedChars"],
            "budget": budget,
            "omissionReasons": omission_reasons,
        },
        "days": days,
        "segments": segment_output,
        "messages": messages,
        "drillDownHandles": [
            {"segmentId": segment["segmentId"], "threadId": segment["threadId"], "eventCount": len(segment["selectedEvents"]), "operation": "activity-segment"}
            for segment in period_segments
        ],
        "verification": {
            "status": "local-authoritative",
            "provenanceComplete": all(bool(message.get("sourceRef")) and bool(message.get("eventId")) for message in messages),
            "claimPolicy": "evidence pack only; no generated factual summary",
            "outOfWindowEventCount": 0,
        },
        "latency": {"totalMs": round((time.perf_counter() - started) * 1000, 3)},
    }
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a provenance-preserving temporal context pack.")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--timezone", "--tz", required=True, dest="timezone")
    parser.add_argument("--mode", choices=sorted(MODE_BUDGETS), default="standard")
    parser.add_argument("--max-messages", type=int)
    parser.add_argument("--max-chars", type=int)
    parser.add_argument("--thread", action="append", dest="threads")
    parser.add_argument("--segment", dest="drill_down")
    parser.add_argument("--range-json", type=Path)
    parser.add_argument("--node", default="node")
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
    metadata = None
    if args.range_json:
        try:
            metadata = json.loads(args.range_json.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            payload = {"status": "error", "code": "INVALID_RANGE_METADATA", "message": str(exc)}
            write_output(payload, args.out)
            return 1
    try:
        payload = build_context(
            args.db.resolve(), args.start, args.end, args.timezone, args.mode,
            args.max_messages, args.max_chars, args.threads, args.drill_down, args.node, metadata,
        )
        write_output(payload, args.out)
        return 0
    except (TemporalContextError, TemporalIndexError) as exc:
        payload = {"status": "error", "code": getattr(exc, "code", "TEMPORAL_CONTEXT_ERROR"), "message": str(exc)}
        write_output(payload, args.out)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
