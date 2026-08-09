#!/usr/bin/env python3
"""Atomically normalize projected and prior source titles to a provider-safe limit."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("State must be a JSON object")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def normalize(state: dict[str, Any], limit: int) -> dict[str, int]:
    current = 0
    prior = 0
    for thread in (state.get("threads") or {}).values():
        for part in thread.get("parts") or []:
            title = str(part.get("title") or "")
            if len(title) > limit:
                part["title"] = title[:limit]
                current += 1
        for old in thread.get("previousSources") or []:
            title = str(old.get("title") or "")
            if len(title) > limit:
                old["title"] = title[:limit]
                prior += 1
    return {"currentTitlesNormalized": current, "priorTitlesNormalized": prior}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--max-chars", type=int, default=189)
    args = parser.parse_args()
    if args.max_chars < 80:
        parser.error("--max-chars must be >= 80 to preserve full lineage")
    path = args.state.resolve()
    state = read_json(path)
    counts = normalize(state, args.max_chars)
    atomic_json(path, state)
    print(json.dumps({**counts, "maxChars": args.max_chars}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
