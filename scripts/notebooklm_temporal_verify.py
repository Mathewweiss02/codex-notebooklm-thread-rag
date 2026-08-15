#!/usr/bin/env python3
"""Verify a source-scoped NotebookLM answer against local temporal evidence.

This verifier is intentionally conservative. It does not claim to prove the
semantics of arbitrary prose. It accepts a remote answer only when local
coverage is complete, the disposable response is not a follow-up, citations
stay inside the current source map, cited passages match selected local event
text, and explicit ISO dates stay inside the selected local dates.

The output is aggregate-only: answer text, cited passages, raw source IDs, and
local message content never leave the in-memory verification boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTRACT = "temporal-claim-verifier-v1"
DATE_LITERAL = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
TIMESTAMP_LITERAL = re.compile(
    r"\b20\d{2}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:?\d{2})\b"
)
CITATION_MARKER = re.compile(r"(?:\[(\d+)\]|【(\d+)】)")
TOKEN = re.compile(r"[\w]+", re.UNICODE)
MIN_CITED_TEXT_CHARS = 24
MIN_CITED_TEXT_TOKENS = 4


class TemporalVerifyError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TemporalVerifyError("INVALID_INPUT", f"cannot read JSON input: {path.name}") from exc


def root_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TemporalVerifyError("INVALID_INPUT", "JSON input must be an object")
    nested = value.get("result")
    return nested if isinstance(nested, dict) else value


def normalize_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def token_match(value: str) -> list[str]:
    return [token.casefold() for token in TOKEN.findall(unicoded(value))]


def unicoded(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value))


def cited_text_supported(cited_text: Any, event_texts: list[str]) -> bool:
    if not isinstance(cited_text, str):
        return False
    candidate = normalize_match(cited_text)
    if len(candidate) < MIN_CITED_TEXT_CHARS:
        return False
    candidate_tokens = token_match(candidate)
    if len(candidate_tokens) < MIN_CITED_TEXT_TOKENS:
        return False
    for event_text in event_texts:
        haystack = normalize_match(event_text)
        if candidate in haystack or haystack in candidate:
            return True
        haystack_tokens = token_match(haystack)
        if len(candidate_tokens) <= len(haystack_tokens):
            width = len(candidate_tokens)
            for start in range(0, len(haystack_tokens) - width + 1):
                if haystack_tokens[start : start + width] == candidate_tokens:
                    return True
    return False


def parse_iso_date(value: str) -> str | None:
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError:
        return None


def explicit_temporal_literals(answer: str) -> tuple[list[str], list[str]]:
    dates = DATE_LITERAL.findall(answer)
    timestamps = TIMESTAMP_LITERAL.findall(answer)
    return dates, timestamps


def answer_date_check(answer: str, context: dict[str, Any]) -> dict[str, Any]:
    messages = [item for item in context.get("messages") or [] if isinstance(item, dict)]
    local_dates = {str(item.get("localDate")) for item in messages if item.get("localDate")}
    dates, timestamps = explicit_temporal_literals(answer)
    invalid_dates = [value for value in dates if parse_iso_date(value) is None]
    out_of_range_dates = [value for value in dates if value not in local_dates and value not in invalid_dates]
    out_of_range_timestamps: list[str] = []
    resolved = context.get("resolvedRange") or {}
    start_utc = str(resolved.get("startUtc") or "")
    end_utc = str(resolved.get("endUtc") or "")
    try:
        start = datetime.fromisoformat(start_utc.replace("Z", "+00:00")) if start_utc else None
        end = datetime.fromisoformat(end_utc.replace("Z", "+00:00")) if end_utc else None
    except ValueError:
        start = None
        end = None
        invalid_dates.append("resolved-range")
    for literal in timestamps:
        try:
            parsed = datetime.fromisoformat(literal.replace("Z", "+00:00"))
        except ValueError:
            out_of_range_timestamps.append(literal)
            continue
        if parsed.tzinfo is None:
            # A naive timestamp cannot be interpreted safely without the
            # caller's local-time rules; reject it instead of guessing.
            out_of_range_timestamps.append(literal)
            continue
        parsed_utc = parsed.astimezone(timezone.utc)
        if start is None or end is None or not (start <= parsed_utc < end):
            out_of_range_timestamps.append(literal)
    return {
        "dateLiteralCount": len(dates),
        "timestampLiteralCount": len(timestamps),
        "invalidDateCount": len(invalid_dates),
        "outOfRangeDateCount": len(out_of_range_dates),
        "outOfRangeTimestampCount": len(out_of_range_timestamps),
        "checkedLocalDateCount": len(local_dates),
        "status": "ok" if not (invalid_dates or out_of_range_dates or out_of_range_timestamps) else "invalid",
    }


def verify_remote_payload(payload: Any, context_value: Any, source_map_value: Any) -> dict[str, Any]:
    """Return an aggregate verdict without returning answer/source content."""

    context = root_payload(context_value)
    source_map = root_payload(source_map_value)
    answer_payload = root_payload(payload)
    codes: list[str] = []

    context_status = str(context.get("status") or "")
    coverage = context.get("coverage") if isinstance(context.get("coverage"), dict) else {}
    included = int(coverage.get("includedEventCount") or 0)
    canonical = int(coverage.get("canonicalEventCount") or 0)
    complete_local = (
        context_status == "ok"
        and coverage.get("completeSelection") is True
        and included == canonical
        and canonical > 0
    )
    if not complete_local:
        codes.append("LOCAL_CONTEXT_INCOMPLETE")

    mapping = source_map.get("mapping") if isinstance(source_map.get("mapping"), list) else []
    source_map_ok = source_map.get("status") == "ok" and bool(mapping)
    source_to_thread: dict[str, str] = {}
    source_to_digest: dict[str, str] = {}
    duplicate_sources = 0
    for item in mapping:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("sourceId") or "")
        thread_id = str(item.get("threadId") or "")
        if not source_id or not thread_id:
            source_map_ok = False
            continue
        if source_id in source_to_thread and source_to_thread[source_id] != thread_id:
            duplicate_sources += 1
        source_to_thread[source_id] = thread_id
        if item.get("sourceSha256"):
            source_to_digest[source_id] = str(item["sourceSha256"])
    if duplicate_sources:
        source_map_ok = False
        codes.append("SOURCE_MAPPING_DUPLICATE")
    if not source_map_ok:
        codes.append("SOURCE_MAPPING_UNVERIFIED")

    if not isinstance(answer_payload, dict):
        codes.append("REMOTE_INVALID")
        answer_payload = {}
    answer = str(answer_payload.get("answer") or answer_payload.get("text") or "")
    if not answer.strip():
        codes.append("REMOTE_ANSWER_EMPTY")
    if answer_payload.get("is_follow_up") is True or answer_payload.get("isFollowUp") is True:
        codes.append("CONVERSATION_STATEFUL")

    references = answer_payload.get("references") or answer_payload.get("sources") or []
    if not isinstance(references, list):
        references = []
        codes.append("REFERENCES_INVALID")
    allowed_source_ids = set(source_to_thread)
    reference_summaries: list[dict[str, Any]] = []
    reference_numbers: set[int] = set()
    referenced_ids: set[str] = set()
    unsupported_reference_count = 0
    out_of_scope_reference_count = 0
    source_file_drift_count = 0
    local_source_files = source_map.get("localSourceFiles") if isinstance(source_map.get("localSourceFiles"), dict) else {}
    marker_numbers = {int(first or second) for first, second in CITATION_MARKER.findall(answer)}
    for index, reference in enumerate(references, start=1):
        if not isinstance(reference, dict):
            reference_summaries.append({"citationNumber": index, "supported": False, "answerSpanValid": False})
            continue
        source_id = str(reference.get("source_id") or reference.get("sourceId") or reference.get("id") or "")
        citation_number_value = reference.get("citation_number") or reference.get("citationNumber")
        try:
            citation_number = int(citation_number_value) if citation_number_value is not None else index
        except (TypeError, ValueError):
            citation_number = index
        if citation_number in reference_numbers:
            codes.append("CITATION_NUMBER_DUPLICATE")
        reference_numbers.add(citation_number)
        if not source_id or source_id not in allowed_source_ids:
            out_of_scope_reference_count += 1
            reference_summaries.append({"citationNumber": citation_number, "supported": False, "answerSpanValid": False})
            continue
        referenced_ids.add(source_id)
        thread_id = source_to_thread[source_id]
        event_texts = [
            str(message.get("text") or "")
            for message in context.get("messages") or []
            if isinstance(message, dict) and str(message.get("threadId") or "") == thread_id
        ]
        local_file_value = local_source_files.get(source_id)
        if local_file_value:
            local_file = Path(str(local_file_value))
            if not local_file.is_file():
                codes.append("LOCAL_SOURCE_FILE_UNAVAILABLE")
            else:
                try:
                    observed_digest = hashlib.sha256(local_file.read_bytes()).hexdigest()
                    if source_to_digest.get(source_id) and observed_digest != source_to_digest[source_id]:
                        source_file_drift_count += 1
                        codes.append("SOURCE_FILE_DRIFT")
                    event_texts.append(local_file.read_text(encoding="utf-8-sig"))
                except (OSError, UnicodeError):
                    codes.append("LOCAL_SOURCE_FILE_UNAVAILABLE")
        supported = cited_text_supported(reference.get("cited_text") or reference.get("citedText"), event_texts)
        answer_start = reference.get("answer_start_char")
        answer_end = reference.get("answer_end_char")
        answer_span_valid = True
        if answer_start is not None or answer_end is not None:
            try:
                answer_span_valid = 0 <= int(answer_start) <= int(answer_end) <= len(answer)
            except (TypeError, ValueError):
                answer_span_valid = False
        reference_summaries.append({"citationNumber": citation_number, "supported": supported, "answerSpanValid": answer_span_valid})

    used_reference_summaries = [
        item for item in reference_summaries
        if not marker_numbers or int(item["citationNumber"]) in marker_numbers
    ]
    unsupported_reference_count = sum(
        not bool(item.get("supported") and item.get("answerSpanValid"))
        for item in used_reference_summaries
    )

    if not references:
        codes.append("CITATION_FREE_CLAIM")
    if marker_numbers and not marker_numbers.issubset(reference_numbers):
        codes.append("CITATION_MARKER_MISMATCH")
    if references and not marker_numbers:
        codes.append("CITATION_MARKER_MISSING")
    if out_of_scope_reference_count:
        codes.append("SOURCE_SCOPE_INVALID")
    if unsupported_reference_count:
        codes.append("CITATION_EVIDENCE_UNMATCHED")

    temporal = answer_date_check(answer, context)
    if temporal["status"] != "ok":
        codes.append("TEMPORAL_LITERAL_OUT_OF_RANGE")

    unique_codes = list(dict.fromkeys(codes))
    blocking = {
        "LOCAL_CONTEXT_INCOMPLETE", "SOURCE_MAPPING_UNVERIFIED", "SOURCE_MAPPING_DUPLICATE",
        "REMOTE_INVALID", "REMOTE_ANSWER_EMPTY", "CONVERSATION_STATEFUL", "REFERENCES_INVALID",
        "CITATION_FREE_CLAIM", "CITATION_MARKER_MISMATCH", "CITATION_MARKER_MISSING",
        "SOURCE_SCOPE_INVALID", "CITATION_EVIDENCE_UNMATCHED", "TEMPORAL_LITERAL_OUT_OF_RANGE",
        "LOCAL_SOURCE_FILE_UNAVAILABLE", "SOURCE_FILE_DRIFT",
    }
    decision = "accept" if not (set(unique_codes) & blocking) else "abstain"
    status = "ok" if decision == "accept" else ("degraded" if not complete_local or not source_map_ok else "abstained")
    return {
        "contractVersion": CONTRACT,
        "status": status,
        "decision": decision,
        "codes": unique_codes,
        "localEvidence": {
            "status": context_status,
            "complete": complete_local,
            "canonicalEventCount": canonical,
            "includedEventCount": included,
            "threadCount": len({str(item.get("threadId")) for item in context.get("messages") or [] if isinstance(item, dict) and item.get("threadId")}),
        },
        "sourceScope": {
            "status": source_map.get("status"),
            "mappedPartCount": len(mapping),
            "referencedSourceCount": len(referenced_ids),
            "outOfScopeReferenceCount": out_of_scope_reference_count,
            "localSourceFileCount": len(local_source_files),
            "localSourceFileDriftCount": source_file_drift_count,
        },
        "citations": {
            "markerCount": len(marker_numbers),
            "referenceCount": len(references),
            "supportedReferenceCount": sum(bool(item.get("supported") and item.get("answerSpanValid")) for item in used_reference_summaries),
            "unsupportedReferenceCount": unsupported_reference_count,
            "scopeValid": out_of_scope_reference_count == 0,
        },
        "temporalLiterals": temporal,
        "answerSha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
        "answerChars": len(answer),
    }


def write_output(payload: dict[str, Any], destination: Path | None) -> None:
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if destination is None:
        sys.stdout.write(serialized)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(serialized, encoding="utf-8", newline="\n")
    temporary.replace(destination)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a source-scoped NotebookLM answer against local temporal evidence.")
    parser.add_argument("--context-pack", required=True, type=Path)
    parser.add_argument("--source-map", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path, help="JSON response path, or - to read one response from stdin")
    parser.add_argument("--out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = parse_args(argv or sys.argv[1:])
    try:
        context = read_json(args.context_pack.resolve())
        source_map = read_json(args.source_map.resolve())
        if str(args.response) == "-":
            response = json.load(sys.stdin)
        else:
            response = read_json(args.response.resolve())
        result = verify_remote_payload(response, context, source_map)
        write_output(result, args.out.resolve() if args.out else None)
        return 0 if result["status"] == "ok" else 1
    except (TemporalVerifyError, json.JSONDecodeError) as exc:
        payload = {"contractVersion": CONTRACT, "status": "error", "decision": "abstain", "codes": [getattr(exc, "code", "INVALID_INPUT")]}
        write_output(payload, args.out.resolve() if args.out else None)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
