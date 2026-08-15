#!/usr/bin/env python3
"""Create a benchmark promotion certificate only after causal evidence passes."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any

from thread_rag_benchmark_causal_audit import (
    CausalAuditError,
    audit_packet,
    read_json,
    repository_root,
    safe_reference,
    sha256_file,
)


CONTRACT = "thread-rag-benchmark-promotion-v1"
REQUIRED_GATES = frozenset(
    {
        "candidateRecall100",
        "hybridTop1",
        "falsePositiveRate",
        "falseNegativeRate",
    }
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def relative_reference(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise CausalAuditError("promotion artifacts must remain inside the repository") from exc


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def promote_packet(score_path: Path, causal_packet_path: Path, output_path: Path) -> dict[str, Any]:
    root = repository_root(causal_packet_path)
    score = read_json(score_path.resolve())
    if not isinstance(score, dict):
        raise CausalAuditError("score report must be a JSON object")
    if score.get("passed") is not True:
        raise CausalAuditError("benchmark score did not pass its quantitative gates")
    gates = score.get("gates")
    if not isinstance(gates, dict) or not REQUIRED_GATES.issubset(gates):
        raise CausalAuditError("benchmark score is missing a required quantitative gate")
    if any(gates[name] is not True for name in REQUIRED_GATES):
        raise CausalAuditError("benchmark score has a false quantitative gate")

    packet = read_json(causal_packet_path.resolve())
    if not isinstance(packet, dict):
        raise CausalAuditError("causal packet must be a JSON object")
    packet_score_path = safe_reference(root, (packet.get("benchmark") or {}).get("scoreReport"))
    if packet_score_path.resolve() != score_path.resolve():
        raise CausalAuditError("causal packet is bound to a different score report")
    causal_result = audit_packet(causal_packet_path.resolve())
    if causal_result.get("status") != "pass":
        raise CausalAuditError("causal evidence did not pass its independent audit")

    score_reference = relative_reference(root, score_path)
    packet_reference = relative_reference(root, causal_packet_path)
    certificate = {
        "contractVersion": CONTRACT,
        "status": "pass",
        "promotedAt": now_iso(),
        "scoreReport": score_reference,
        "scoreReportSha256": sha256_file(score_path.resolve()),
        "causalPacket": packet_reference,
        "causalPacketSha256": sha256_file(causal_packet_path.resolve()),
        "quantitativeGates": gates,
        "causalAudit": {
            "status": causal_result["status"],
            "caseCount": causal_result.get("caseCount"),
            "failureCaseCount": causal_result.get("failureCaseCount"),
            "independentCheckCount": causal_result.get("independentCheckCount"),
            "claimedImprovementCount": causal_result.get("claimedImprovementCount"),
        },
    }
    atomic_json(output_path.resolve(), certificate)
    return certificate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score-report", required=True, type=Path)
    parser.add_argument("--causal-packet", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        certificate = promote_packet(args.score_report, args.causal_packet, args.out)
    except (CausalAuditError, OSError, json.JSONDecodeError) as exc:
        certificate = {"contractVersion": CONTRACT, "status": "invalid", "errors": [str(exc)]}
        atomic_json(args.out.resolve(), certificate)
    print(json.dumps(certificate, indent=2))
    return 0 if certificate["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
