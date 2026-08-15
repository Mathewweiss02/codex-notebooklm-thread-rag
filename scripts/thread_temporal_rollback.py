#!/usr/bin/env python3
"""Rehearse a digest-paired rollback of derived temporal state.

Rollback never edits canonical Codex sessions or NotebookLM state.  It only
restores the prior handoff/index pair retained by the temporal refresh path,
and it refuses to act unless both generations independently verify and agree.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import thread_temporal_index as index  # noqa: E402
from thread_temporal_refresh import refresh_lock  # noqa: E402


class TemporalRollbackError(RuntimeError):
    """Expected fail-closed rollback failure."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _summary(handoff: Path, database: Path) -> dict[str, Any]:
    try:
        handoff_value = index.load_handoff(handoff)
        database_value = index.verify_database(database)
    except (OSError, index.TemporalIndexError) as exc:
        raise TemporalRollbackError("ROLLBACK_SOURCE_INVALID", "rollback generation failed verification") from exc
    handoff_manifest = str(handoff_value["header"].get("manifestDigest") or "")
    handoff_events = str(handoff_value["trailer"].get("eventDigest") or "")
    if database_value.get("manifestDigest") != handoff_manifest or database_value.get("eventDigest") != handoff_events:
        raise TemporalRollbackError("ROLLBACK_GENERATION_MISMATCH", "handoff and index digests do not agree")
    return {
        "manifestDigest": handoff_manifest,
        "eventDigest": handoff_events,
        "eventCount": int(database_value.get("eventCount") or 0),
        "schemaVersion": int(database_value.get("schemaVersion") or 0),
    }


def _replace_pair(root: Path, handoff: Path, database: Path, prior_handoff: Path, prior_database: Path) -> None:
    backup_handoff = root / f".{handoff.name}.rollback-current-{os.getpid()}.tmp"
    backup_database = root / f".{database.name}.rollback-current-{os.getpid()}.tmp"
    staged_handoff = root / f".{handoff.name}.rollback-staged-{os.getpid()}.tmp"
    staged_database = root / f".{database.name}.rollback-staged-{os.getpid()}.tmp"
    try:
        shutil.copy2(handoff, backup_handoff)
        shutil.copy2(database, backup_database)
        shutil.copy2(prior_handoff, staged_handoff)
        shutil.copy2(prior_database, staged_database)
        os.replace(staged_handoff, handoff)
        os.replace(staged_database, database)
        _summary(handoff, database)
    except (OSError, TemporalRollbackError) as exc:
        try:
            if backup_handoff.exists():
                os.replace(backup_handoff, handoff)
            if backup_database.exists():
                os.replace(backup_database, database)
        except OSError as restore_exc:
            raise TemporalRollbackError("ROLLBACK_RECOVERY_FAILED", "rollback failed and current state could not be restored") from restore_exc
        if isinstance(exc, TemporalRollbackError):
            raise
        raise TemporalRollbackError("ROLLBACK_PROMOTION_FAILED", "rollback generation could not be promoted") from exc
    finally:
        for path in (backup_handoff, backup_database, staged_handoff, staged_database):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def rollback(root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    root = root.resolve()
    handoff = root / "temporal-events.ndjson"
    database = root / "temporal.sqlite3"
    prior_handoff = Path(f"{handoff}.previous")
    prior_database = Path(f"{database}.previous")
    for path in (handoff, database, prior_handoff, prior_database):
        if not path.is_file():
            raise TemporalRollbackError("ROLLBACK_ARTIFACT_MISSING", "current and previous temporal generations are required")
    with refresh_lock(root):
        current = _summary(handoff, database)
        prior = _summary(prior_handoff, prior_database)
        result = {
            "status": "dry-run" if dry_run else "ok",
            "current": current,
            "previous": prior,
            "changed": current["eventDigest"] != prior["eventDigest"] or current["manifestDigest"] != prior["manifestDigest"],
        }
        if dry_run:
            return result
        _replace_pair(root, handoff, database, prior_handoff, prior_database)
        restored = _summary(handoff, database)
        result["restored"] = restored
        result["canonicalStateTouched"] = False
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(rollback(args.root, dry_run=args.dry_run), separators=(",", ":")))
        return 0
    except TemporalRollbackError as exc:
        print(json.dumps({"status": "error", "code": exc.code}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
