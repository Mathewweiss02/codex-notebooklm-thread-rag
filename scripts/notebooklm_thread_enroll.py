#!/usr/bin/env python3
"""Atomically enroll newly visible Codex tasks after projection and live source-cap gates."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from notebooklm import NotebookLMClient


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def atomic_json(path: Path, value: dict[str, Any], *, backup: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if backup and path.is_file():
        shutil.copy2(path, path.with_name(f"{path.stem}.previous{path.suffix}"))
    os.replace(temporary, path)


def run_checked(command: list[str], label: str, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else f"exit {completed.returncode}"
        raise RuntimeError(f"{label} failed: {detail}")
    return completed


def merge_scope(existing: list[str], visible: list[str]) -> tuple[list[str], list[str]]:
    output = list(dict.fromkeys(str(item) for item in existing if item))
    known = set(output)
    added: list[str] = []
    for thread_id in visible:
        if thread_id not in known:
            output.append(thread_id)
            known.add(thread_id)
            added.append(thread_id)
    return output, added


def state_part_counts(state: dict[str, Any], scope: set[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for thread_id, thread in (state.get("threads") or {}).items():
        if thread_id not in scope:
            continue
        parts = thread.get("parts") or []
        if not parts:
            raise ValueError(f"Task {thread_id} has no projected source parts")
        counts[thread_id] = len(parts)
    return counts


def source_ids_in_state(state: dict[str, Any]) -> set[str]:
    output: set[str] = set()
    for thread in (state.get("threads") or {}).values():
        for part in list(thread.get("parts") or []) + list(thread.get("previousSources") or []):
            source_id = str(part.get("sourceId") or "")
            if source_id:
                output.add(source_id)
    return output


def pending_part_count(state: dict[str, Any], scope: set[str]) -> int:
    count = 0
    for thread_id, thread in (state.get("threads") or {}).items():
        if thread_id in scope:
            count += sum(1 for part in thread.get("parts") or [] if not part.get("sourceId"))
    return count


def capacity_decision(
    part_counts: dict[str, int],
    *,
    live_sources: int,
    pending_parts: int,
    source_limit: int,
    requested_reserve: int,
) -> dict[str, Any]:
    if not part_counts:
        raise ValueError("No projected tasks are available for capacity planning")
    largest = max(part_counts.values())
    reserve = max(requested_reserve, largest)
    steady_capacity = source_limit - reserve
    steady_sources = sum(part_counts.values())
    immediate_sources = live_sources + pending_parts
    return {
        "sourceLimit": source_limit,
        "requestedReserve": requested_reserve,
        "effectiveReserve": reserve,
        "steadyCapacity": steady_capacity,
        "steadySources": steady_sources,
        "steadyHeadroom": steady_capacity - steady_sources,
        "liveSources": live_sources,
        "pendingParts": pending_parts,
        "immediateSources": immediate_sources,
        "largestTaskParts": largest,
        "safe": steady_sources <= steady_capacity and immediate_sources <= source_limit,
    }


def projection_base_command(config: dict[str, Any], output_root: Path) -> list[str]:
    return [
        str(config["NodePath"]),
        str(config["ProjectionScript"]),
        "--device", str(config["Device"]),
        "--out", str(output_root),
        "--quiet-minutes", "0",
        "--hard-max-hours", str(config.get("HardMaxHours", 6)),
        "--max-words", str(config.get("MaxWords", 120000)),
        "--max-message-chars", str(config.get("MaxMessageChars", 100000)),
        "--max-line-bytes", str(config.get("MaxLineBytes", 8388608)),
    ]


async def enroll(config_path: Path, apply: bool) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = read_json(config_path)
    if config.get("AllowAllThreads") is True:
        return {"status": "allow-all", "applied": False, "addedTasks": 0}
    existing_scope = [str(item) for item in config.get("ThreadIds") or [] if item]
    if not existing_scope:
        raise ValueError("Explicit scope is empty")
    root = Path(config["ProjectionRoot"]).resolve()
    state_path = root / "state.json"
    current_state = read_json(state_path) if state_path.is_file() else {"threads": {}}
    unscoped_state = set(current_state.get("threads") or {}) - set(existing_scope)
    if unscoped_state:
        raise ValueError(f"Projection state contains {len(unscoped_state)} tasks outside explicit scope")

    with tempfile.TemporaryDirectory(prefix="thread-rag-enroll-") as temporary:
        staging = Path(temporary)
        inventory_path = staging / "inventory.json"
        inventory_command = projection_base_command(config, staging) + ["--inventory-out", str(inventory_path)]
        run_checked(inventory_command, "task inventory")
        inventory = read_json(inventory_path)
        visible_ids = [str(item["id"]) for item in inventory.get("threads") or [] if item.get("id")]
        merged_scope, new_ids = merge_scope(existing_scope, visible_ids)
        visible_set = set(visible_ids)
        current_threads = current_state.get("threads") or {}
        missing_projected = [thread_id for thread_id in existing_scope if thread_id in visible_set and thread_id not in current_threads]
        stage_ids = list(dict.fromkeys(new_ids + missing_projected))
        if not stage_ids:
            return {
                "status": "current",
                "applied": False,
                "visibleTasks": len(visible_ids),
                "enrolledTasks": len(existing_scope),
                "addedTasks": 0,
            }

        staged_root = staging / "projected"
        stage_command = projection_base_command(config, staged_root) + ["--force"]
        for thread_id in stage_ids:
            stage_command.extend(["--thread", thread_id])
        run_checked(stage_command, "staged projection")
        staged_state = read_json(staged_root / "state.json")
        staged_threads = staged_state.get("threads") or {}
        missing_stage = set(stage_ids) - set(staged_threads)
        if missing_stage:
            raise ValueError(f"Staged projection did not produce {len(missing_stage)} required tasks")

        target_scope = set(merged_scope)
        counts = state_part_counts(current_state, target_scope)
        counts.update(state_part_counts(staged_state, target_scope))
        missing_counts = target_scope - set(counts)
        if missing_counts:
            raise ValueError(f"Capacity plan lacks projections for {len(missing_counts)} enrolled tasks")
        pending = pending_part_count(current_state, set(existing_scope)) + sum(len(staged_threads[thread_id]["parts"]) for thread_id in stage_ids)

        async with NotebookLMClient.from_storage(profile=str(config["Profile"])) as client:
            sources = await client.sources.list(str(config["NotebookId"]), strict=True)
            limits = await client.settings.get_account_limits()
        live_ids = {source.id for source in sources}
        known_ids = source_ids_in_state(current_state)
        untracked = live_ids - known_ids
        if config.get("RejectUntrackedSources") is True and untracked:
            raise ValueError(f"Dedicated retrieval notebook contains {len(untracked)} untracked sources")
        decision = capacity_decision(
            counts,
            live_sources=len(live_ids),
            pending_parts=pending,
            source_limit=int(limits.source_limit),
            requested_reserve=int(config.get("SourceReserve", 60)),
        )
        if not decision["safe"]:
            raise ValueError(
                "Enrollment exceeds source budget: "
                f"steady={decision['steadySources']}/{decision['steadyCapacity']} "
                f"immediate={decision['immediateSources']}/{decision['sourceLimit']}"
            )
        if apply and new_ids:
            config["ThreadIds"] = merged_scope
            config["LastEnrollmentAt"] = now_iso()
            atomic_json(config_path, config, backup=True)
        return {
            "status": "enrolled" if apply and new_ids else "planned",
            "applied": bool(apply and new_ids),
            "visibleTasks": len(visible_ids),
            "enrolledTasks": len(merged_scope),
            "addedTasks": len(new_ids),
            "repairedMissingProjections": len(missing_projected),
            "capacity": decision,
        }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    report = await enroll(args.config, args.apply)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
