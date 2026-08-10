#!/usr/bin/env python3
"""Plan or apply bounded, lineage-aware retention for local thread-RAG artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


REVISION_RE = re.compile(r"^r(?P<revision>\d+)-p\d+\.md$")


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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


def require_descendant(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    resolved_root = root.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(f"Retention target escapes guarded root: {resolved}") from error
    return resolved


def report_kind(path: Path) -> str:
    name = path.name.casefold()
    for prefix in ("runner-", "upload-", "retrieval-", "retention-"):
        if name.startswith(prefix):
            return prefix[:-1]
    return "projection" if re.match(r"^\d{4}-\d{2}-\d{2}t", name) else "other"


def report_failed(path: Path) -> bool:
    try:
        value = read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return True
    if str(value.get("status") or value.get("Status") or "").casefold() == "error":
        return True
    if int(value.get("errors") or 0) > 0:
        return True
    summary = value.get("summary") or {}
    return summary.get("thresholdPassed") is False


def projection_keep_set(state: dict[str, Any], projections_root: Path, revisions_to_keep: int) -> set[Path]:
    keep: set[Path] = set()
    for thread in (state.get("threads") or {}).values():
        for part in list(thread.get("parts") or []) + list(thread.get("previousSources") or []):
            file_value = part.get("file")
            if file_value:
                keep.add(require_descendant(Path(file_value), projections_root))
    for thread_dir in (path for path in projections_root.iterdir() if path.is_dir()):
        revisions: dict[int, list[Path]] = {}
        for path in thread_dir.glob("r*-p*.md"):
            match = REVISION_RE.match(path.name)
            if match:
                revisions.setdefault(int(match.group("revision")), []).append(path.resolve())
        for revision in sorted(revisions, reverse=True)[:revisions_to_keep]:
            keep.update(revisions[revision])
    return keep


def report_delete_set(files: list[Path], max_count: int, retention_days: int, now: datetime) -> set[Path]:
    ordered = sorted(files, key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    protected: set[Path] = set()
    seen_kind: set[str] = set()
    seen_failed_kind: set[str] = set()
    for path in ordered:
        kind = report_kind(path)
        if kind not in seen_kind:
            protected.add(path.resolve())
            seen_kind.add(kind)
        if kind not in seen_failed_kind and report_failed(path):
            protected.add(path.resolve())
            seen_failed_kind.add(kind)
    cutoff = now - timedelta(days=retention_days)
    output: set[Path] = set()
    for index, path in enumerate(ordered):
        resolved = path.resolve()
        modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        if resolved not in protected and (index >= max_count or modified < cutoff):
            output.add(resolved)
    return output


def build_plan(
    root: Path,
    *,
    state_path: Path | None = None,
    search_root: Path | None = None,
    projection_revisions: int = 1,
    retention_days: int = 30,
    max_run_reports: int = 100,
    max_search_reports: int = 100,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    state_path = (state_path or root / "state.json").resolve()
    if state_path != root / "state.json":
        require_descendant(state_path, root)
    if not state_path.is_file():
        raise ValueError(f"Retention requires projection state: {state_path}")
    projections_root = root / "projections"
    if not projections_root.is_dir():
        raise ValueError(f"Retention requires projections directory: {projections_root}")
    if projection_revisions < 1 or retention_days < 1 or max_run_reports < 1 or max_search_reports < 1:
        raise ValueError("Retention bounds must all be positive")

    state = read_json(state_path)
    keep = projection_keep_set(state, projections_root, projection_revisions)
    projection_files = [require_descendant(path, projections_root) for path in projections_root.rglob("r*-p*.md")]
    projection_delete = set(projection_files) - keep

    current_time = now or datetime.now(UTC)
    runs_root = root / "runs"
    run_files = [require_descendant(path, runs_root) for path in runs_root.glob("*.json")] if runs_root.is_dir() else []
    run_delete = report_delete_set(run_files, max_run_reports, retention_days, current_time)

    search_delete: set[Path] = set()
    resolved_search_root: Path | None = None
    if search_root:
        resolved_search_root = search_root.resolve()
        if resolved_search_root.name.casefold() != "search-runs":
            raise ValueError("Search retention root must be a directory named search-runs")
        search_files = [require_descendant(path, resolved_search_root) for path in resolved_search_root.glob("*.json")] if resolved_search_root.is_dir() else []
        search_delete = report_delete_set(search_files, max_search_reports, retention_days, current_time)

    actions: list[dict[str, Any]] = []
    for kind, base, paths in (
        ("projection", root, projection_delete),
        ("run-report", root, run_delete),
        ("search-report", resolved_search_root, search_delete),
    ):
        if base is None:
            continue
        for path in sorted(paths):
            actions.append({"kind": kind, "path": str(path.relative_to(base)), "bytes": path.stat().st_size})
    return {
        "generatedAt": now_iso(),
        "root": str(root),
        "bounds": {
            "projectionRevisions": projection_revisions,
            "retentionDays": retention_days,
            "maxRunReports": max_run_reports,
            "maxSearchReports": max_search_reports,
        },
        "protectedProjectionFiles": len(keep),
        "actions": actions,
        "candidateFiles": len(actions),
        "candidateBytes": sum(item["bytes"] for item in actions),
    }


def apply_plan(plan: dict[str, Any], root: Path, search_root: Path | None = None) -> None:
    root = root.resolve()
    resolved_search = search_root.resolve() if search_root else None
    for action in plan["actions"]:
        base = resolved_search if action["kind"] == "search-report" else root
        if base is None:
            raise ValueError("Search report action has no guarded root")
        target = require_descendant(base / action["path"], base)
        if target.is_file():
            target.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--search-root", type=Path)
    parser.add_argument("--projection-revisions", type=int, default=1)
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--max-run-reports", type=int, default=40)
    parser.add_argument("--max-search-reports", type=int, default=100)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    plan = build_plan(
        root,
        state_path=args.state.resolve() if args.state else None,
        search_root=args.search_root.resolve() if args.search_root else None,
        projection_revisions=args.projection_revisions,
        retention_days=args.retention_days,
        max_run_reports=args.max_run_reports,
        max_search_reports=args.max_search_reports,
    )
    if args.apply:
        apply_plan(plan, root, args.search_root)
    plan["status"] = "applied" if args.apply else "planned"
    output = args.out or root / "runs" / f"retention-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{os.getpid()}.json"
    atomic_json(output, plan)
    print(json.dumps({"status": plan["status"], "candidateFiles": plan["candidateFiles"], "candidateBytes": plan["candidateBytes"], "report": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
