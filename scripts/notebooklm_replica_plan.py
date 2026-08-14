#!/usr/bin/env python3
"""Model isolated NotebookLM retrieval-notebook pools without creating them."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


CONTRACT = "notebooklm-replica-plan-v1"


class ReplicaPlanError(ValueError):
    pass


def build_replica_plan(
    *,
    source_parts: int,
    source_limit: int,
    notebook_limit: int,
    reserve: int,
    existing_notebooks: int,
    current_retrieval_notebooks: int,
    pool_sizes: list[int],
) -> dict[str, Any]:
    values = {
        "source_parts": source_parts,
        "source_limit": source_limit,
        "notebook_limit": notebook_limit,
        "reserve": reserve,
        "existing_notebooks": existing_notebooks,
        "current_retrieval_notebooks": current_retrieval_notebooks,
    }
    if any(value < 1 for value in values.values()):
        raise ReplicaPlanError("all counts and limits must be positive")
    if current_retrieval_notebooks > existing_notebooks:
        raise ReplicaPlanError("current retrieval notebooks cannot exceed existing notebooks")
    if not pool_sizes or any(size < 1 for size in pool_sizes):
        raise ReplicaPlanError("pool sizes must be positive")
    if source_limit <= reserve:
        raise ReplicaPlanError("source limit must exceed the reserve")

    steady_capacity = source_limit - reserve
    if source_parts > steady_capacity:
        raise ReplicaPlanError(
            f"one replica needs {source_parts} source parts, above steady capacity {steady_capacity}"
        )

    rows: list[dict[str, Any]] = []
    for pool_size in sorted(set(pool_sizes)):
        new_replicas = max(0, pool_size - current_retrieval_notebooks)
        notebooks_after = existing_notebooks + new_replicas
        source_headroom = source_limit - source_parts
        steady_headroom = steady_capacity - source_parts
        rows.append(
            {
                "retrievalPoolSize": pool_size,
                "newReplicaCount": new_replicas,
                "notebooksAfter": notebooks_after,
                "notebookHeadroomAfter": notebook_limit - notebooks_after,
                "sourcePartsPerReplica": source_parts,
                "sourceHeadroomPerReplica": source_headroom,
                "steadyHeadroomPerReplica": steady_headroom,
                "aggregateSourceCopies": source_parts * pool_size,
                "initialCopyUnits": source_parts * new_replicas,
                "worstCaseRefreshUnits": source_parts * pool_size,
                "capacitySafe": notebooks_after <= notebook_limit and steady_headroom >= 0,
            }
        )

    return {
        "contractVersion": CONTRACT,
        "sourceParts": source_parts,
        "sourceLimit": source_limit,
        "notebookLimit": notebook_limit,
        "requestedReserve": reserve,
        "steadyCapacityPerReplica": steady_capacity,
        "existingNotebooks": existing_notebooks,
        "currentRetrievalNotebooks": current_retrieval_notebooks,
        "poolSizes": sorted(set(pool_sizes)),
        "plans": rows,
        "liveCreation": "not authorized by this planner",
    }


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-parts", required=True, type=int)
    parser.add_argument("--source-limit", required=True, type=int)
    parser.add_argument("--notebook-limit", required=True, type=int)
    parser.add_argument("--reserve", required=True, type=int)
    parser.add_argument("--existing-notebooks", required=True, type=int)
    parser.add_argument("--current-retrieval-notebooks", required=True, type=int)
    parser.add_argument("--pool-sizes", nargs="+", type=int, default=[1, 2, 4, 8])
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv or sys.argv[1:])
    try:
        plan = build_replica_plan(
            source_parts=args.source_parts,
            source_limit=args.source_limit,
            notebook_limit=args.notebook_limit,
            reserve=args.reserve,
            existing_notebooks=args.existing_notebooks,
            current_retrieval_notebooks=args.current_retrieval_notebooks,
            pool_sizes=args.pool_sizes,
        )
        atomic_json(args.out.resolve(), plan)
        print(json.dumps({
            "status": "ok",
            "contractVersion": CONTRACT,
            "poolSizes": plan["poolSizes"],
            "steadyCapacityPerReplica": plan["steadyCapacityPerReplica"],
            "plans": plan["plans"],
            "out": str(args.out.resolve()),
        }))
        return 0
    except ReplicaPlanError as exc:
        print(json.dumps({"status": "error", "code": "INVALID_REPLICA_PLAN", "message": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
