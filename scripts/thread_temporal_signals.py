"""Extract conservative, provenance-backed activity signals from events.

The temporal index remains the authority for event identity and content.  This
module only labels language patterns in already-sanitized events.  A signal is
never a factual summary: it is a heuristic pointer to evidence that a caller
may inspect or cite.
"""

from __future__ import annotations

import re
from typing import Any, Iterable


CONTRACT = "temporal-signals-v1"
MAX_PREVIEW_CHARS = 240


_RULES: dict[str, tuple[tuple[str, re.Pattern[str], frozenset[str] | None], ...]] = {
    "intent": (
        ("explicit-request", re.compile(r"\b(?:i\s+(?:want|need)|we\s+need|please|can\s+you|could\s+you|let['’]?s|help\s+me|trying\s+to|goal\s+is|plan\s+to)\b", re.I), frozenset({"user"})),
        ("action-question", re.compile(r"\b(?:should\s+we|how\s+do\s+we|what\s+should\s+i|where\s+can\s+i)\b", re.I), frozenset({"user"})),
    ),
    "completion": (
        ("completion-language", re.compile(r"\b(?:implemented|completed|finished|fixed|resolved|verified|passed|created|built|shipped|done|successfully|working)\b", re.I), None),
        ("test-success-language", re.compile(r"\b(?:tests?|checks?|gates?)\s+(?:pass(?:ed)?|green|succeed(?:ed)?)\b", re.I), None),
    ),
    "unresolved": (
        ("open-item-language", re.compile(r"\b(?:still|todo|tbd|pending|blocked|unresolved|not\s+yet|remaining|needs?\s+to|need\s+to|failed|error|broken|can['’]?t|cannot|unknown|figure\s+out|follow[- ]?up|open\s+(?:question|item))\b", re.I), None),
    ),
    "artifact": (
        ("artifact-path", re.compile(r"(?:\b[A-Za-z]:[\\/][^\s<>\"']+|\b(?:[\w.-]+[\\/])+[\w.-]+\b)"), None),
        ("artifact-file", re.compile(r"\b[\w.-]+\.(?:py|mjs|js|ps1|json|jsonl|md|sqlite3|db|yaml|yml|toml|csv|txt|zip|pdf|png|xlsx?)\b", re.I), None),
        ("artifact-link", re.compile(r"\bhttps?://[^\s<>\"']+", re.I), None),
        ("artifact-identifier", re.compile(r"\b(?:[0-9a-f]{7,40}|(?:PR|issue|#)\s*\d+)\b", re.I), None),
    ),
    "decision": (
        ("decision-language", re.compile(r"\b(?:decided|choose|chosen|selected|will\s+use|going\s+with|keep\s+as|reject(?:ed)?|approved|default|policy)\b", re.I), None),
    ),
}


def _preview(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= MAX_PREVIEW_CHARS:
        return compact
    return compact[: MAX_PREVIEW_CHARS - 1].rstrip() + "…"


def _evidence(event: dict[str, Any], kind: str, rule: str) -> dict[str, Any]:
    source_ref = event.get("sourceRef")
    if not isinstance(source_ref, dict):
        source_ref = {}
    return {
        "kind": kind,
        "rule": rule,
        "confidence": "heuristic",
        "eventId": str(event["eventId"]),
        "threadId": str(event["threadId"]),
        "role": str(event["role"]),
        "timestampUtc": str(event["timestampUtc"]),
        "textDigest": str(event["textDigest"]),
        "sourceRef": {
            "sourceKind": source_ref.get("sourceKind"),
            "sourceFileDigest": source_ref.get("sourceFileDigest"),
            "lineNumber": source_ref.get("lineNumber"),
        },
        "preview": _preview(str(event["text"])),
    }


def extract_signals(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return conservative labels for the supplied, already-selected events.

    Signals are intentionally generated only from the caller's included event
    set.  A budgeted context pack therefore cannot imply evidence that was
    omitted from the pack.
    """
    grouped: dict[str, list[dict[str, Any]]] = {kind: [] for kind in _RULES}
    seen: set[tuple[str, str]] = set()
    ordered = sorted(events, key=lambda event: (str(event.get("timestampUtc") or ""), str(event.get("threadId") or ""), str(event.get("eventId") or "")))
    for event in ordered:
        text = str(event.get("text") or "")
        role = str(event.get("role") or "")
        if not text or role not in {"user", "assistant"}:
            continue
        for kind, rules in _RULES.items():
            for label, pattern, roles in rules:
                if roles is not None and role not in roles:
                    continue
                if not pattern.search(text):
                    continue
                identity = (kind, str(event.get("eventId") or ""))
                if identity not in seen:
                    grouped[kind].append(_evidence(event, kind, label))
                    seen.add(identity)
                break

    counts = {kind: len(values) for kind, values in grouped.items()}
    return {
        "contractVersion": CONTRACT,
        "scope": "included-events",
        "confidencePolicy": "heuristic labels require inspection of linked event evidence",
        "signals": grouped,
        "counts": counts,
        "totalCount": sum(counts.values()),
    }


def validate_signals(payload: dict[str, Any], events: Iterable[dict[str, Any]]) -> None:
    """Fail closed if a signal points outside the supplied event set."""
    if payload.get("contractVersion") != CONTRACT:
        raise ValueError("signal contract mismatch")
    event_map = {str(event["eventId"]): event for event in events}
    for kind, values in (payload.get("signals") or {}).items():
        if kind not in _RULES or not isinstance(values, list):
            raise ValueError("invalid signal category")
        for signal in values:
            event_id = str(signal.get("eventId") or "")
            if event_id not in event_map:
                raise ValueError("signal points outside event scope")
            event = event_map[event_id]
            for field in ("threadId", "role", "timestampUtc", "textDigest"):
                if signal.get(field) != event.get(field):
                    raise ValueError(f"signal {field} does not match event")
            source_ref = signal.get("sourceRef")
            event_source_ref = event.get("sourceRef")
            if not isinstance(source_ref, dict) or not isinstance(event_source_ref, dict):
                raise ValueError("signal source reference is invalid")
            for field in ("sourceKind", "sourceFileDigest", "lineNumber"):
                if source_ref.get(field) != event_source_ref.get(field):
                    raise ValueError(f"signal source reference {field} does not match event")
