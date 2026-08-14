"""Independent slow oracle for TM-003 extractor parity.

This intentionally does not import the production Node parser. It implements
the visible-message and redaction contract independently for small fixtures and
compares canonical event signatures with the extractor handoff.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTRACT = "temporal-event-v1"
POLICY = "visible-messages-secrets-redacted-v4"


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return None
        utc = parsed.astimezone(timezone.utc)
        return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"
    except (TypeError, ValueError, OverflowError):
        return None


def text_from_content(content: Any) -> str:
    items = content if isinstance(content, list) else [content]
    parts: list[str] = []
    for item in items:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
        elif isinstance(item, dict) and isinstance(item.get("content"), str):
            parts.append(item["content"])
    return "\n".join(part for part in parts if part)


def load_patterns() -> list[tuple[str, re.Pattern[str]]]:
    contract_path = Path(__file__).resolve().parents[2] / "scripts" / "redaction_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for entry in contract["patterns"]:
        flags = re.IGNORECASE if "i" in entry.get("flags", "") else 0
        patterns.append((entry["label"], re.compile(entry["pattern"], flags)))
    return patterns


PATTERNS = load_patterns()


def replacement(label: str, match: re.Match[str]) -> str:
    value = match.group(0)
    if label == "url-credential":
        return re.sub(r"//[^@]+@", "//[REDACTED]@", value, count=1)
    if label == "user-home-path":
        return "[USERPROFILE]" + ("\\" if value.endswith("\\") or value.endswith("/") else "")
    if label == "unix-home-path":
        return "[USERPROFILE]" + ("/" if value.endswith("/") else "")
    if label == "query-secret":
        return f"{match.group(1)}[REDACTED]"
    if label == "named-secret":
        name_match = re.match(r"^\s*([^:=]+)\s*[:=]", value)
        name = name_match.group(1).strip() if name_match else "secret"
        return f"{name}=[REDACTED]"
    if label == "authorization":
        scheme = "Basic" if re.search(r"Basic", value, re.IGNORECASE) else "Bearer"
        return f"{scheme} [REDACTED]"
    return f"[REDACTED_{label.upper().replace('-', '_')}]"


def sanitize(value: str) -> str:
    text = value.replace("\x00", "")
    for label, pattern in PATTERNS:
        text = pattern.sub(lambda match: replacement(label, match), text)
    return text


def truncate(value: str, limit: int = 100_000) -> str:
    if len(value) <= limit:
        return value
    marker = f"\n\n[TRUNCATED_MIDDLE original_chars={len(value)} sha256={sha256(value)}]\n\n"
    keep = max(1, limit - len(marker))
    first = (keep + 1) // 2
    last = keep // 2
    return value[:first] + marker + value[-last:]


def read_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("threads")
    if not isinstance(rows, list):
        raise ValueError("manifest must be an array or contain threads")
    result = []
    for row in rows:
        if not row.get("id") or not row.get("path"):
            raise ValueError("manifest thread needs id and path")
        result.append({
            "id": str(row["id"]),
            "path": (path.parent / str(row["path"])).resolve(),
            "archived": bool(row.get("archived")),
        })
    return sorted(result, key=lambda row: row["id"])


def source_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_expected(manifest_path: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    expected: list[dict[str, Any]] = []
    stats = {"malformedLines": 0, "duplicateMessages": 0, "quarantineCount": 0}
    for thread in read_manifest(manifest_path):
        digest = source_digest(thread["path"])
        seen: set[str] = set()
        for line_number, raw_line in enumerate(thread["path"].read_text(encoding="utf-8").splitlines(), 1):
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                stats["malformedLines"] += 1
                continue
            if event.get("type") != "response_item" or event.get("payload", {}).get("type") != "message":
                continue
            payload = event["payload"]
            role = payload.get("role")
            if role not in {"user", "assistant"}:
                continue
            raw_text = text_from_content(payload.get("content"))
            if not raw_text.strip():
                continue
            text = truncate(sanitize(raw_text).strip())
            original_timestamp = event.get("timestamp") or ""
            duplicate_key = sha256("\x00".join([role, original_timestamp, text]))
            if duplicate_key in seen:
                stats["duplicateMessages"] += 1
                continue
            seen.add(duplicate_key)
            timestamp_utc = parse_timestamp(event.get("timestamp"))
            source_ref = {
                "sourceKind": "archive" if thread["archived"] else "active",
                "sourceFileDigest": digest,
                "lineNumber": line_number,
            }
            if timestamp_utc is None:
                stats["quarantineCount"] += 1
                continue
            expected.append({
                "recordType": "event",
                "contractVersion": CONTRACT,
                "eventId": sha256("\x00".join([thread["id"], role, timestamp_utc, text])),
                "threadId": thread["id"],
                "role": role,
                "timestampUtc": timestamp_utc,
                "text": text,
                "textDigest": sha256(text),
                "sourceRef": source_ref,
            })
    return expected, stats


def signature(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventId": event["eventId"],
        "threadId": event["threadId"],
        "role": event["role"],
        "timestampUtc": event["timestampUtc"],
        "textDigest": event["textDigest"],
        "sourceRef": event["sourceRef"],
    }


def signature_digest(events: list[dict[str, Any]]) -> str:
    payload = json.dumps([signature(event) for event in events], ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return sha256(payload)


def read_handoff(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    trailer: dict[str, Any] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(raw_line)
        if record.get("recordType") == "event":
            events.append(record)
        elif record.get("recordType") == "trailer":
            trailer = record
    return events, trailer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--handoff", type=Path)
    args = parser.parse_args()
    expected, stats = build_expected(args.manifest.resolve())
    payload: dict[str, Any] = {
        "contractVersion": CONTRACT,
        "policyVersion": POLICY,
        "expectedEventCount": len(expected),
        "quarantineCount": stats["quarantineCount"],
        "malformedLines": stats["malformedLines"],
        "duplicateMessages": stats["duplicateMessages"],
        "oracleDigest": signature_digest(expected),
        "handoffParity": None,
    }
    if args.handoff:
        actual, trailer = read_handoff(args.handoff.resolve())
        actual_signatures = [signature(event) for event in actual]
        expected_signatures = [signature(event) for event in expected]
        parity = actual_signatures == expected_signatures
        payload["handoffParity"] = parity
        payload["actualEventCount"] = len(actual)
        payload["actualSignatureDigest"] = signature_digest(actual)
        payload["trailerEventCount"] = trailer.get("eventCount")
        payload["trailerQuarantineCount"] = trailer.get("quarantineCount")
        if not parity:
            payload["firstMismatch"] = next((index for index, pair in enumerate(zip(expected_signatures, actual_signatures)) if pair[0] != pair[1]), min(len(expected_signatures), len(actual_signatures)))
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.handoff and not payload["handoffParity"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
