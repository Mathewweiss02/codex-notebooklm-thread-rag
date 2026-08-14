#!/usr/bin/env python3
"""Refresh the local temporal index from one stable projection-state snapshot.

The projection state and canonical Codex JSONL remain authoritative.  This
helper deliberately stages the manifest, extractor handoff, and a temporary
SQLite index before changing the production derived state.  A malformed or
changing source therefore leaves the last known-good temporal index intact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import thread_temporal_index as temporal_index  # noqa: E402


class TemporalRefreshError(RuntimeError):
    """Expected fail-closed refresh error with a stable machine code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TemporalRefreshError("STATE_INVALID", "projection state could not be read") from exc
    if not isinstance(value, dict):
        raise TemporalRefreshError("STATE_INVALID", "projection state must be an object")
    return value


def _validate_state(path: Path) -> int:
    state = _read_json_object(path)
    if state.get("policyVersion") != temporal_index.POLICY:
        raise TemporalRefreshError("POLICY_MISMATCH", "projection policy is not the approved visibility policy")
    threads = state.get("threads")
    if not isinstance(threads, dict) or not threads:
        raise TemporalRefreshError("STATE_EMPTY", "projection state contains no threads")
    return len(threads)


def _child_creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0


def _run_child(
    executable: str,
    arguments: Sequence[str],
    label: str,
    timeout_seconds: float,
) -> None:
    try:
        completed = subprocess.run(
            [executable, *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            creationflags=_child_creation_flags(),
        )
    except FileNotFoundError as exc:
        raise TemporalRefreshError("RUNTIME_UNAVAILABLE", f"{label} executable is unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise TemporalRefreshError("RUNTIME_TIMEOUT", f"{label} exceeded its bounded timeout") from exc
    except OSError as exc:
        raise TemporalRefreshError("RUNTIME_ERROR", f"{label} could not be started") from exc
    if completed.returncode != 0:
        # Classify only stable machine-facing diagnostics. Do not echo child
        # output: it can contain local paths or source text.
        child_text = f"{completed.stdout}\n{completed.stderr}"
        if "source-changed-during-scan" in child_text:
            code = "SOURCE_CHANGED_DURING_SCAN"
        elif "session-path-missing" in child_text:
            code = "SESSION_PATH_MISSING"
        elif "visible-message-line-exceeded-limit" in child_text:
            code = "VISIBLE_LINE_LIMIT"
        else:
            code = "RUNTIME_ERROR"
        raise TemporalRefreshError(code, f"{label} exited unsuccessfully")


def _argument_value(arguments: Sequence[str], name: str) -> Path:
    try:
        return Path(arguments[arguments.index(name) + 1])
    except (ValueError, IndexError) as exc:
        raise TemporalRefreshError("INTERNAL_ERROR", f"{name} was not supplied to the staged command") from exc


def _promote_handoff(staged: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.copy2(destination, Path(f"{destination}.previous"))
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.staging")
    try:
        shutil.copy2(staged, temporary)
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _materialize_stable_sources(manifest_path: Path, source_root: Path) -> None:
    """Copy source files so active Codex threads cannot change mid-extract."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TemporalRefreshError("MANIFEST_INVALID", "temporal manifest was not valid JSON") from exc
    threads = manifest.get("threads") if isinstance(manifest, dict) else None
    if not isinstance(threads, list) or not threads:
        raise TemporalRefreshError("MANIFEST_INVALID", "temporal manifest contains no threads")
    source_root.mkdir(parents=True, exist_ok=True)
    for index, thread in enumerate(threads):
        if not isinstance(thread, dict) or not thread.get("path"):
            raise TemporalRefreshError("MANIFEST_INVALID", "temporal manifest contains an invalid source")
        source = Path(str(thread["path"])).resolve()
        if not source.is_file():
            raise TemporalRefreshError("SESSION_PATH_MISSING", "temporal source file is unavailable")
        before = _file_digest(source)
        destination = source_root / f"source-{index:05d}.jsonl"
        try:
            shutil.copy2(source, destination)
        except OSError as exc:
            raise TemporalRefreshError("SOURCE_SNAPSHOT_FAILED", "temporal source could not be staged") from exc
        after = _file_digest(source)
        if before != after:
            raise TemporalRefreshError("SOURCE_CHANGED_DURING_SNAPSHOT", "a canonical source changed during staging")
        thread.setdefault("canonicalPath", str(source))
        thread["path"] = str(destination)
    try:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise TemporalRefreshError("MANIFEST_WRITE_FAILED", "staged temporal manifest could not be written") from exc


def _summarize_handoff(handoff: dict[str, Any]) -> dict[str, Any]:
    header = handoff["header"]
    trailer = handoff["trailer"]
    return {
        "manifestDigest": str(header.get("manifestDigest") or ""),
        "eventDigest": str(trailer.get("eventDigest") or ""),
        "eventCount": int(trailer.get("eventCount") or 0),
        "quarantineCount": int(trailer.get("quarantineCount") or 0),
        "malformedLines": int(trailer.get("malformedLines") or 0),
        "overflowLines": int(trailer.get("overflowLines") or 0),
        "overflowVisibleLines": int(trailer.get("overflowVisibleLines") or 0),
        "duplicateMessages": int(trailer.get("duplicateMessages") or 0),
    }


def refresh(
    *,
    state_path: Path,
    root: Path,
    node_path: str,
    manifest_script: Path | None = None,
    extract_script: Path | None = None,
    timeout_seconds: float = 300.0,
    max_message_chars: int = 100_000,
    max_line_bytes: int = 8 * 1024 * 1024,
    snapshot_attempts: int = 3,
    allow_diagnostics: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    state_path = state_path.resolve()
    root = root.resolve()
    if timeout_seconds <= 0:
        raise TemporalRefreshError("INVALID_TIMEOUT", "timeout must be positive")
    if max_message_chars < 1 or max_line_bytes < 1:
        raise TemporalRefreshError("INVALID_LIMIT", "message and line limits must be positive")
    if snapshot_attempts < 1:
        raise TemporalRefreshError("INVALID_ATTEMPTS", "snapshot attempts must be positive")
    state_thread_count = _validate_state(state_path)
    root.mkdir(parents=True, exist_ok=True)
    manifest_script = (manifest_script or SCRIPT_DIR / "thread_temporal_manifest.mjs").resolve()
    extract_script = (extract_script or SCRIPT_DIR / "thread_temporal_extract.mjs").resolve()
    production_handoff = root / "temporal-events.ndjson"
    production_db = root / "temporal.sqlite3"

    with tempfile.TemporaryDirectory(prefix=".temporal-refresh-", dir=root) as temporary_root:
        temporary_root_path = Path(temporary_root)
        snapshot = temporary_root_path / "state.json"
        manifest = temporary_root_path / "manifest.json"
        handoff = temporary_root_path / "temporal-events.ndjson"
        staged_db = temporary_root_path / "temporal.sqlite3"
        shutil.copy2(state_path, snapshot)
        snapshot_thread_count = _validate_state(snapshot)
        if snapshot_thread_count != state_thread_count:
            raise TemporalRefreshError("STATE_CHANGED", "projection state changed while being snapshotted")

        staged_summary: dict[str, Any] | None = None
        for attempt in range(snapshot_attempts):
            try:
                manifest_args = [
                    str(manifest_script),
                    "--state",
                    str(snapshot),
                    "--out",
                    str(manifest),
                ]
                _run_child(node_path, manifest_args, "temporal manifest", timeout_seconds)
                source_root = temporary_root_path / "sources"
                if source_root.exists():
                    shutil.rmtree(source_root)
                _materialize_stable_sources(manifest, source_root)
                try:
                    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise TemporalRefreshError("MANIFEST_INVALID", "temporal manifest was not valid JSON") from exc
                if not isinstance(manifest_payload, dict) or int(manifest_payload.get("missingThreadCount") or 0) != 0:
                    raise TemporalRefreshError("THREAD_SCOPE_INCOMPLETE", "temporal manifest did not locate every state thread")
                if int(manifest_payload.get("threadCount") or 0) != snapshot_thread_count:
                    raise TemporalRefreshError("THREAD_COUNT_MISMATCH", "temporal manifest count differs from state snapshot")

                extract_args = [
                    str(extract_script),
                    "--thread-manifest",
                    str(manifest),
                    "--out",
                    str(handoff),
                    "--max-message-chars",
                    str(max_message_chars),
                    "--max-line-bytes",
                    str(max_line_bytes),
                ]
                _run_child(node_path, extract_args, "temporal extraction", timeout_seconds)
                try:
                    staged_summary = _summarize_handoff(temporal_index.load_handoff(handoff))
                except temporal_index.TemporalIndexError as exc:
                    raise TemporalRefreshError("HANDOFF_INVALID", "temporal extractor produced an invalid handoff") from exc
                break
            except TemporalRefreshError as exc:
                retryable = exc.code in {"SOURCE_CHANGED_DURING_SNAPSHOT", "SOURCE_CHANGED_DURING_SCAN"}
                if not retryable or attempt + 1 >= snapshot_attempts:
                    raise
        if staged_summary is None:
            raise TemporalRefreshError("STAGE_FAILED", "temporal source stage did not produce a handoff")
        diagnostics = {
            key: staged_summary[key]
            for key in ("quarantineCount", "malformedLines", "overflowLines", "overflowVisibleLines", "duplicateMessages")
            if staged_summary[key]
        }
        blocking_diagnostics = {
            key: diagnostics[key]
            for key in ("quarantineCount", "malformedLines", "overflowVisibleLines")
            if key in diagnostics
        }
        if blocking_diagnostics and not allow_diagnostics:
            raise TemporalRefreshError("SOURCE_DIAGNOSTICS", "temporal extraction reported source diagnostics")
        try:
            staged_index = temporal_index.build_index(handoff, staged_db, rebuild=True)
            staged_verified = temporal_index.verify_database(staged_db)
        except temporal_index.TemporalIndexError as exc:
            raise TemporalRefreshError("INDEX_STAGE_FAILED", "temporary temporal index failed verification") from exc

        current: dict[str, Any] | None = None
        current_valid = False
        if production_db.exists():
            try:
                current = temporal_index.verify_database(production_db)
                current_valid = True
            except temporal_index.TemporalIndexError:
                current = None

        same_index = bool(
            current
            and current.get("manifestDigest") == staged_summary["manifestDigest"]
            and current.get("eventDigest") == staged_summary["eventDigest"]
        )
        changed = not same_index
        recovered_current_index = False
        if not dry_run and changed:
            try:
                if current_valid:
                    temporal_index.build_index(handoff, production_db, rebuild=False)
                else:
                    temporal_index.build_index(handoff, production_db, rebuild=True)
                    recovered_current_index = True
            except temporal_index.TemporalIndexError as exc:
                raise TemporalRefreshError("INDEX_PROMOTION_FAILED", "production temporal index was not updated") from exc

        if not dry_run and (changed or not production_handoff.exists()):
            try:
                _promote_handoff(handoff, production_handoff)
            except OSError as exc:
                raise TemporalRefreshError("HANDOFF_PROMOTION_FAILED", "production temporal handoff was not updated") from exc

        if dry_run:
            final_summary = staged_summary
            final_index = staged_verified
        else:
            try:
                final_index = temporal_index.verify_database(production_db)
                final_summary = _summarize_handoff(temporal_index.load_handoff(production_handoff))
            except (OSError, temporal_index.TemporalIndexError) as exc:
                raise TemporalRefreshError("POST_PROMOTION_VERIFY_FAILED", "promoted temporal state failed verification") from exc
            if (
                final_index.get("manifestDigest") != final_summary["manifestDigest"]
                or final_index.get("eventDigest") != final_summary["eventDigest"]
            ):
                raise TemporalRefreshError("POST_PROMOTION_MISMATCH", "temporal index and handoff digests differ")

    return {
        "status": "dry-run" if dry_run else "ok",
        "changed": changed,
        "recoveredCurrentIndex": recovered_current_index,
        "stateThreadCount": state_thread_count,
        "threadCount": int(final_index.get("threadCount") or state_thread_count),
        "eventCount": int(final_index.get("eventCount") or final_summary["eventCount"]),
        "sourceReferenceCount": int(final_index.get("sourceReferenceCount") or 0),
        "quarantineCount": int(final_index.get("quarantineCount") or final_summary["quarantineCount"]),
        "manifestDigest": final_summary["manifestDigest"],
        "eventDigest": final_summary["eventDigest"],
        "diagnostics": diagnostics,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--node", required=True)
    parser.add_argument("--manifest-script", type=Path)
    parser.add_argument("--extract-script", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--max-message-chars", type=int, default=100_000)
    parser.add_argument("--max-line-bytes", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--snapshot-attempts", type=int, default=3)
    parser.add_argument("--allow-diagnostics", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        result = refresh(
            state_path=args.state,
            root=args.root,
            node_path=args.node,
            manifest_script=args.manifest_script,
            extract_script=args.extract_script,
            timeout_seconds=args.timeout_seconds,
            max_message_chars=args.max_message_chars,
            max_line_bytes=args.max_line_bytes,
            snapshot_attempts=args.snapshot_attempts,
            allow_diagnostics=args.allow_diagnostics,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except TemporalRefreshError as exc:
        print(json.dumps({"status": "error", "code": exc.code}, separators=(",", ":")))
        return 1
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "code": "UNEXPECTED_ERROR"}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
