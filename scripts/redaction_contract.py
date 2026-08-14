"""Shared redaction contract for text sent to remote NotebookLM surfaces."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any


CONTRACT_PATH = Path(__file__).with_name("redaction_contract.json")
CONTRACT: dict[str, Any] = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
POLICY = str(CONTRACT["policy"])


def _compile(entry: dict[str, Any]) -> re.Pattern[str]:
    flags = re.IGNORECASE if "i" in str(entry.get("flags") or "") else 0
    return re.compile(str(entry["pattern"]), flags)


PATTERNS = [(str(entry["label"]), _compile(entry)) for entry in CONTRACT["patterns"]]


def _replacement(label: str, match: re.Match[str]) -> str:
    value = match.group(0)
    if label == "url-credential":
        return re.sub(r"//[^@]+@", "//[REDACTED]@", value, count=1)
    if label == "user-home-path":
        return "[USERPROFILE]\\" if value.endswith(("\\", "/")) else "[USERPROFILE]"
    if label == "unix-home-path":
        return "[USERPROFILE]/" if value.endswith("/") else "[USERPROFILE]"
    if label == "query-secret":
        return f"{match.group(1)}[REDACTED]"
    if label == "named-secret":
        name = re.match(r"^\s*([^:=]+)\s*[:=]", value)
        return f"{name.group(1).strip() if name else 'secret'}=[REDACTED]"
    if label == "authorization":
        return f"{'Basic' if re.search(r'Basic', value, re.IGNORECASE) else 'Bearer'} [REDACTED]"
    return f"[REDACTED_{label.upper().replace('-', '_')}]"


def sanitize_remote_text(value: str) -> tuple[str, dict[str, int]]:
    text = str(value or "").replace("\x00", "")
    counts: dict[str, int] = {}
    for label, pattern in PATTERNS:
        text, count = pattern.subn(lambda match: _replacement(label, match), text)
        if count:
            counts[label] = counts.get(label, 0) + count
    return text, counts


def summarize_error(error: BaseException) -> str:
    """Describe an error without echoing a remote request or response."""

    message = str(error)
    return (
        f"{type(error).__name__}: details redacted "
        f"(messageChars={len(message)}; messageSha256={hashlib.sha256(message.encode('utf-8')).hexdigest()})"
    )
