#!/usr/bin/env python3
"""Validate the executable evidence ledger for the temporal certification matrix.

The matrix is the set of claims.  This ledger is the set of retained results.
The checker deliberately treats ``covered`` as different from ``passed``:
coverage notes and nearby unit tests do not satisfy a release gate until an
executable result, command, and digest are retained for that exact row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTRACT = "temporal-certification-evidence-v1"
ROW_RE = re.compile(r"^\|\s*([A-Z]+-\d{3})\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$")
STATUS_VALUES = {"pending", "covered", "pass", "fail", "blocked"}


class CertificationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CertificationError("INPUT_INVALID", "certification ledger is not readable JSON") from exc
    if not isinstance(value, dict):
        raise CertificationError("INPUT_INVALID", "certification ledger must be a JSON object")
    return value


def parse_matrix(path: Path) -> list[dict[str, str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CertificationError("MATRIX_MISSING", "certification matrix could not be read") from exc
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in lines:
        match = ROW_RE.match(line)
        if not match or match.group(1) == "ID":
            continue
        row_id, scenario, invariant, level = match.groups()
        if row_id in seen:
            raise CertificationError("MATRIX_DUPLICATE", f"matrix row is duplicated: {row_id}")
        seen.add(row_id)
        rows.append({"id": row_id, "scenario": scenario, "invariant": invariant, "testLevel": level})
    if not rows:
        raise CertificationError("MATRIX_EMPTY", "certification matrix has no rows")
    return rows


def matrix_digest(rows: list[dict[str, str]]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def init_ledger(matrix_path: Path, ledger_path: Path) -> dict[str, Any]:
    rows = parse_matrix(matrix_path)
    payload = {
        "contractVersion": CONTRACT,
        "matrixPath": matrix_path.name,
        "matrixDigest": matrix_digest(rows),
        "generatedAt": now_iso(),
        "rows": {
            row["id"]: {
                "status": "pending",
                "scenario": row["scenario"],
                "testLevel": row["testLevel"],
                "evidence": [],
                "notes": "No retained row-specific execution result yet.",
            }
            for row in rows
        },
    }
    atomic_json(ledger_path, payload)
    return payload


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def _repository_root(matrix_path: Path) -> Path:
    """Resolve retained evidence from the repository, not the caller's CWD."""

    resolved = matrix_path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if (parent / ".git").exists():
            return parent
    # Unit fixtures may be intentionally detached from a Git worktree.
    return resolved.parent


def _evidence_digest(matrix_path: Path, reference: str) -> str | None:
    """Return a file digest for a safe relative evidence reference."""

    candidate = Path(reference)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    path = (_repository_root(matrix_path) / candidate).resolve()
    try:
        path.relative_to(_repository_root(matrix_path))
    except ValueError:
        return None
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mark_rows(
    matrix_path: Path,
    ledger_path: Path,
    row_ids: list[str],
    status: str,
    evidence_ref: str,
    result_digest: str | None,
    executed_at: str | None,
    notes: str | None,
) -> dict[str, Any]:
    if status not in STATUS_VALUES or status == "pending":
        raise CertificationError("MARK_INVALID", "mark status must be covered, pass, fail, or blocked")
    rows, ledger, errors = validate_ledger(matrix_path, ledger_path)
    if errors:
        selected = set(row_ids)
        refreshable = {
            error
            for error in errors
            if any(
                error.startswith(f"row {row_id} ")
                and ("resultDigest does not match retained evidence" in error or "without a readable repository evidence file" in error)
                for row_id in selected
            )
        }
        if set(errors) - refreshable:
            raise CertificationError("LEDGER_INVALID", "cannot mark an invalid certification ledger")
    known = {row["id"] for row in rows}
    unknown = sorted(set(row_ids) - known)
    if unknown:
        raise CertificationError("ROW_UNKNOWN", "one or more requested matrix rows are unknown")
    if not evidence_ref.strip():
        raise CertificationError("MARK_INVALID", "an evidence reference is required")
    if status == "pass" and not result_digest:
        raise CertificationError("MARK_INVALID", "a result digest is required for pass")
    values = ledger["rows"]
    for row_id in sorted(set(row_ids)):
        entry = values[row_id]
        entry["status"] = status
        entry["evidence"] = sorted(set([*entry.get("evidence", []), evidence_ref]))
        entry["executedAt"] = executed_at or now_iso()
        if result_digest:
            entry["resultDigest"] = result_digest
        if notes:
            entry["notes"] = notes
    ledger["updatedAt"] = now_iso()
    atomic_json(ledger_path, ledger)
    return summary(rows, ledger, [])


def validate_ledger(matrix_path: Path, ledger_path: Path) -> tuple[list[dict[str, str]], dict[str, Any], list[str]]:
    rows = parse_matrix(matrix_path)
    ledger = read_json(ledger_path)
    if ledger.get("contractVersion") != CONTRACT:
        raise CertificationError("CONTRACT_MISMATCH", "certification ledger contract is unsupported")
    if ledger.get("matrixDigest") != matrix_digest(rows):
        raise CertificationError("MATRIX_DRIFT", "certification matrix changed since the ledger was initialized")
    values = ledger.get("rows")
    if not isinstance(values, dict):
        raise CertificationError("LEDGER_INVALID", "ledger rows must be an object")
    expected = {row["id"] for row in rows}
    actual = set(values)
    errors: list[str] = []
    for row_id in sorted(expected - actual):
        errors.append(f"missing row {row_id}")
    for row_id in sorted(actual - expected):
        errors.append(f"unknown row {row_id}")
    for row_id in sorted(expected & actual):
        entry = values[row_id]
        if not isinstance(entry, dict):
            errors.append(f"row {row_id} is not an object")
            continue
        status = entry.get("status")
        if status not in STATUS_VALUES:
            errors.append(f"row {row_id} has invalid status")
        evidence = entry.get("evidence")
        if not isinstance(evidence, list):
            errors.append(f"row {row_id} evidence is not an array")
        if status == "pass" and not evidence:
            errors.append(f"row {row_id} is pass without evidence")
        if status == "pass" and not entry.get("executedAt"):
            errors.append(f"row {row_id} is pass without executedAt")
        if status == "pass" and not entry.get("resultDigest"):
            errors.append(f"row {row_id} is pass without resultDigest")
        if status == "pass" and entry.get("evidence") and entry.get("resultDigest"):
            expected_digest = str(entry["resultDigest"]).lower()
            evidence_digests = {
                digest
                for reference in entry["evidence"]
                if isinstance(reference, str)
                for digest in [_evidence_digest(matrix_path, reference)]
                if digest
            }
            if not evidence_digests:
                errors.append(f"row {row_id} is pass without a readable repository evidence file")
            elif expected_digest not in evidence_digests:
                errors.append(f"row {row_id} resultDigest does not match retained evidence")
    return rows, ledger, errors


def summary(rows: list[dict[str, str]], ledger: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    values = ledger.get("rows") if isinstance(ledger.get("rows"), dict) else {}
    statuses = Counter(str((values.get(row["id"]) or {}).get("status") or "invalid") for row in rows)
    categories = Counter(row["id"].split("-", 1)[0] for row in rows)
    category_status: dict[str, dict[str, int]] = {}
    for row in rows:
        category = row["id"].split("-", 1)[0]
        status = str((values.get(row["id"]) or {}).get("status") or "invalid")
        category_status.setdefault(category, {})[status] = category_status.setdefault(category, {}).get(status, 0) + 1
    return {
        "contractVersion": CONTRACT,
        "status": "pass" if not errors and statuses.get("pass", 0) == len(rows) else "open",
        "matrixRowCount": len(rows),
        "matrixDigest": ledger.get("matrixDigest"),
        "statusCounts": dict(sorted(statuses.items())),
        "categoryCounts": dict(sorted(categories.items())),
        "categoryStatus": dict(sorted(category_status.items())),
        "validationErrorCount": len(errors),
        "releaseBlockingRowCount": sum(count for status, count in statuses.items() if status != "pass"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--init", action="store_true", help="create a pending ledger from the matrix")
    parser.add_argument("--summary", action="store_true", help="print the current ledger summary (the default read-only action)")
    parser.add_argument("--gate", action="store_true", help="fail unless every matrix row is a retained pass")
    parser.add_argument("--mark", action="store_true", help="update selected row statuses")
    parser.add_argument("--ids", nargs="+", help="matrix row IDs used with --mark")
    parser.add_argument("--status", choices=sorted(STATUS_VALUES - {"pending"}), help="new row status used with --mark")
    parser.add_argument("--evidence", help="short retained evidence reference used with --mark")
    parser.add_argument("--result-digest", help="digest of the retained execution result used with --mark")
    parser.add_argument("--executed-at", help="UTC execution time used with --mark")
    parser.add_argument("--notes", help="short evidence note used with --mark")
    args = parser.parse_args(argv or sys.argv[1:])
    try:
        matrix_path = args.matrix.resolve()
        ledger_path = args.ledger.resolve()
        if args.init:
            payload = init_ledger(matrix_path, ledger_path)
            print(json.dumps({"status": "initialized", "matrixRowCount": len(payload["rows"]), "out": str(ledger_path)}))
            return 0
        if args.mark:
            if not args.ids or not args.status or not args.evidence:
                raise CertificationError("MARK_INVALID", "--mark requires --ids, --status, and --evidence")
            result = mark_rows(
                matrix_path,
                ledger_path,
                args.ids,
                args.status,
                args.evidence,
                args.result_digest,
                args.executed_at,
                args.notes,
            )
            print(json.dumps(result, separators=(",", ":")))
            return 0
        rows, ledger, errors = validate_ledger(matrix_path, ledger_path)
        result = summary(rows, ledger, errors)
        if errors:
            result["status"] = "invalid"
            result["validationErrors"] = errors[:20]
        print(json.dumps(result, separators=(",", ":")))
        if errors or (args.gate and result["status"] != "pass"):
            return 1
        return 0
    except CertificationError as exc:
        print(json.dumps({"status": "error", "code": exc.code}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
