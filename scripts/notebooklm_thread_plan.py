#!/usr/bin/env python3
"""Plan deterministic NotebookLM shards with rolling-update headroom."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REQUIRED_POLICY = "visible-messages-secrets-redacted-v4"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def plan_shards(state: dict[str, Any], source_limit: int, requested_reserve: int, prefix: str) -> dict[str, Any]:
    if state.get("policyVersion") != REQUIRED_POLICY:
        raise ValueError(f"Unsupported projection policy: {state.get('policyVersion')!r}")
    rows: list[dict[str, Any]] = []
    for thread_id, thread in (state.get("threads") or {}).items():
        parts = thread.get("parts") or []
        if not parts:
            raise ValueError(f"Thread {thread_id} has no projected parts")
        rows.append({"threadId": thread_id, "revision": int(thread.get("revision") or 0), "parts": len(parts)})
    if not rows:
        raise ValueError("Projection state has no threads")
    largest = max(row["parts"] for row in rows)
    reserve = max(requested_reserve, largest)
    capacity = source_limit - reserve
    if capacity <= 0:
        raise ValueError(f"No usable capacity: source_limit={source_limit} reserve={reserve}")
    if largest > capacity:
        raise ValueError(f"One thread needs {largest} sources, above shard capacity {capacity}")

    bins: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: (-item["parts"], item["threadId"])):
        target = next((item for item in bins if item["sourceParts"] + row["parts"] <= capacity), None)
        if target is None:
            target = {"sourceParts": 0, "threads": []}
            bins.append(target)
        target["threads"].append(row)
        target["sourceParts"] += row["parts"]

    canonical = json.dumps(sorted(rows, key=lambda item: item["threadId"]), separators=(",", ":"))
    shards = []
    for index, item in enumerate(bins, 1):
        shards.append({
            "index": index,
            "name": f"{prefix}-{index:02d}",
            "sourceParts": item["sourceParts"],
            "steadyHeadroom": source_limit - item["sourceParts"],
            "threads": sorted(item["threads"], key=lambda row: row["threadId"]),
        })
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "policyVersion": REQUIRED_POLICY,
        "stateDigest": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "sourceLimit": source_limit,
        "requestedReserve": requested_reserve,
        "effectiveReserve": reserve,
        "shardCapacity": capacity,
        "threadCount": len(rows),
        "sourceParts": sum(row["parts"] for row in rows),
        "largestThreadParts": largest,
        "shardCount": len(shards),
        "shards": shards,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--source-limit", type=int, default=300)
    parser.add_argument("--reserve", type=int, default=60, help="Minimum sources reserved for rolling revisions")
    parser.add_argument("--prefix", default="Codex-Thread-RAG")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.source_limit < 2 or args.reserve < 1:
        parser.error("--source-limit must be >= 2 and --reserve must be >= 1")
    state_path = args.state.resolve()
    plan = plan_shards(read_json(state_path), args.source_limit, args.reserve, args.prefix)
    output = args.out or state_path.parent / "shard_plan.json"
    atomic_json(output, plan)
    print(json.dumps({key: plan[key] for key in ("threadCount", "sourceParts", "largestThreadParts", "effectiveReserve", "shardCapacity", "shardCount")} | {"plan": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
