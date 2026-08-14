"""Crash-safe SQLite index for temporal-event-v1 handoffs.

The database is derived state. Canonical Codex JSONL and the Node extractor
remain authoritative. This module intentionally has no NotebookLM or auth
dependency so local temporal queries survive remote outages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CONTRACT = "temporal-event-v1"
POLICY = "visible-messages-secrets-redacted-v4"
SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1
THREAD_METADATA_KEY = "threadMetadata"


class TemporalIndexError(RuntimeError):
    """Expected fail-closed index error with a stable machine code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def timestamp_ms(value: str) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise TemporalIndexError("INVALID_TIMESTAMP", "event timestamp must be UTC with a Z suffix")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise TemporalIndexError("INVALID_TIMESTAMP", str(exc)) from exc
    if parsed.tzinfo is None:
        raise TemporalIndexError("INVALID_TIMESTAMP", "timestamp has no timezone")
    return int(parsed.timestamp() * 1000)


def event_identity(event: dict[str, Any]) -> str:
    return sha256("\x00".join([event["threadId"], event["role"], event["timestampUtc"], event["text"]]))


def validate_event(event: dict[str, Any]) -> None:
    required = ("eventId", "contractVersion", "threadId", "role", "timestampUtc", "text", "textDigest", "sourceRef")
    missing = [field for field in required if field not in event]
    if missing:
        raise TemporalIndexError("INVALID_EVENT", "missing fields: " + ",".join(missing))
    if event["contractVersion"] != CONTRACT:
        raise TemporalIndexError("CONTRACT_MISMATCH", "event contract version is unsupported")
    if event["role"] not in {"user", "assistant"}:
        raise TemporalIndexError("INVALID_EVENT", "event role is not visible")
    if not isinstance(event["threadId"], str) or not event["threadId"]:
        raise TemporalIndexError("INVALID_EVENT", "thread ID is empty")
    if not isinstance(event["text"], str) or not event["text"].strip():
        raise TemporalIndexError("INVALID_EVENT", "event text is empty")
    timestamp_ms(event["timestampUtc"])
    if event["eventId"] != event_identity(event):
        raise TemporalIndexError("EVENT_ID_MISMATCH", "event identity does not match canonical fields")
    if event["textDigest"] != sha256(event["text"]):
        raise TemporalIndexError("TEXT_DIGEST_MISMATCH", "event text digest does not match text")
    source_ref = event["sourceRef"]
    if not isinstance(source_ref, dict) or not {"sourceKind", "sourceFileDigest", "lineNumber"}.issubset(source_ref):
        raise TemporalIndexError("INVALID_SOURCE_REF", "source provenance is incomplete")
    if source_ref["sourceKind"] not in {"active", "archive"}:
        raise TemporalIndexError("INVALID_SOURCE_REF", "source kind is unsupported")
    if not isinstance(source_ref["sourceFileDigest"], str) or not source_ref["sourceFileDigest"]:
        raise TemporalIndexError("INVALID_SOURCE_REF", "source file digest is empty")
    if not isinstance(source_ref["lineNumber"], int) or source_ref["lineNumber"] < 1:
        raise TemporalIndexError("INVALID_SOURCE_REF", "source line number is invalid")


def validate_quarantine(record: dict[str, Any]) -> None:
    if record.get("recordType") != "quarantine" or record.get("contractVersion") != CONTRACT:
        raise TemporalIndexError("INVALID_QUARANTINE", "quarantine record contract is invalid")
    if not record.get("threadId") or record.get("reason") not in {"missing-timestamp", "invalid-timestamp"}:
        raise TemporalIndexError("INVALID_QUARANTINE", "quarantine reason or thread is invalid")
    source_ref = record.get("sourceRef") or {}
    if source_ref.get("sourceKind") not in {"active", "archive"} or not source_ref.get("sourceFileDigest") or not isinstance(source_ref.get("lineNumber"), int):
        raise TemporalIndexError("INVALID_QUARANTINE", "quarantine provenance is incomplete")


def validate_thread_metadata(value: Any) -> dict[str, dict[str, Any]]:
    """Validate path-free workspace metadata carried by a temporal handoff."""
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise TemporalIndexError("THREAD_METADATA_INVALID", "thread metadata is not valid JSON") from exc
    if not isinstance(value, dict) or any(not isinstance(key, str) or not key for key in value):
        raise TemporalIndexError("THREAD_METADATA_INVALID", "thread metadata must be keyed by thread ID")
    normalized: dict[str, dict[str, Any]] = {}
    for thread_id, metadata in value.items():
        if not isinstance(metadata, dict):
            raise TemporalIndexError("THREAD_METADATA_INVALID", "thread metadata entries must be objects")
        label = metadata.get("workspaceLabel", "unknown")
        workspace_hash = metadata.get("workspaceHash")
        source = metadata.get("source", "unknown")
        if not isinstance(label, str) or not label or len(label) > 120:
            raise TemporalIndexError("THREAD_METADATA_INVALID", "workspace label is invalid")
        if workspace_hash is not None and (not isinstance(workspace_hash, str) or len(workspace_hash) > 64):
            raise TemporalIndexError("THREAD_METADATA_INVALID", "workspace hash is invalid")
        if not isinstance(metadata.get("archived", False), bool) or not isinstance(source, str):
            raise TemporalIndexError("THREAD_METADATA_INVALID", "thread metadata flags are invalid")
        # Deliberately reject raw cwd/path fields so this sidecar cannot become
        # an accidental private-path transport.
        if any(key in metadata for key in ("cwd", "path", "canonicalPath")):
            raise TemporalIndexError("THREAD_METADATA_INVALID", "raw path metadata is not allowed")
        normalized[thread_id] = {
            "workspaceLabel": label,
            "workspaceHash": workspace_hash,
            "archived": bool(metadata.get("archived", False)),
            "source": source,
        }
    return normalized


def _metadata_from_connection(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    table = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='thread_metadata'"
    ).fetchone()
    if table is None:
        raise TemporalIndexError("INDEX_SCHEMA_MISMATCH", "thread metadata table is missing")
    rows = connection.execute(
        "SELECT thread_id,workspace_label,workspace_hash,archived,source FROM thread_metadata ORDER BY thread_id"
    ).fetchall()
    if rows:
        return validate_thread_metadata({
            row[0]: {
                "workspaceLabel": row[1],
                "workspaceHash": row[2],
                "archived": bool(row[3]),
                "source": row[4],
            }
            for row in rows
        })
    row = connection.execute("SELECT value FROM meta WHERE key=?", (THREAD_METADATA_KEY,)).fetchone()
    return validate_thread_metadata(row[0] if row else {})


def load_handoff(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise TemporalIndexError("HANDOFF_MISSING", "handoff file does not exist")
    header: dict[str, Any] | None = None
    trailer: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []
    quarantines: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    event_hash = hashlib.sha256()
    record_count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise TemporalIndexError("HANDOFF_MALFORMED", f"line {line_number}: {exc.msg}") from exc
            record_count += 1
            record_type = record.get("recordType")
            if record_type == "header":
                if header is not None or line_number != 1:
                    raise TemporalIndexError("HANDOFF_ORDER", "header must be the first record")
                if record.get("contractVersion") != CONTRACT or record.get("policyVersion") != POLICY:
                    raise TemporalIndexError("CONTRACT_MISMATCH", "handoff header contract or policy is unsupported")
                header = record
            elif record_type == "event":
                if header is None or trailer is not None:
                    raise TemporalIndexError("HANDOFF_ORDER", "event is outside header/trailer")
                validate_event(record)
                prior = seen.get(record["eventId"])
                if prior is not None:
                    canonical_fields = ("eventId", "contractVersion", "threadId", "role", "timestampUtc", "text", "textDigest")
                    if any(prior[field] != record[field] for field in canonical_fields):
                        raise TemporalIndexError("EVENT_ID_COLLISION", "same event ID has different canonical fields")
                else:
                    seen[record["eventId"]] = record
                events.append(record)
                canonical_line = raw_line.rstrip("\r\n") + "\n"
                event_hash.update(canonical_line.encode("utf-8"))
            elif record_type == "quarantine":
                if header is None or trailer is not None:
                    raise TemporalIndexError("HANDOFF_ORDER", "quarantine is outside header/trailer")
                validate_quarantine(record)
                quarantines.append(record)
            elif record_type == "trailer":
                if header is None or trailer is not None:
                    raise TemporalIndexError("HANDOFF_ORDER", "invalid trailer position")
                trailer = record
            else:
                raise TemporalIndexError("HANDOFF_RECORD", f"unsupported record type at line {line_number}")
    if header is None or trailer is None:
        raise TemporalIndexError("HANDOFF_INCOMPLETE", "header and trailer are required")
    if trailer.get("contractVersion") != CONTRACT:
        raise TemporalIndexError("CONTRACT_MISMATCH", "trailer contract is unsupported")
    if trailer.get("eventCount") != len(events) or trailer.get("quarantineCount") != len(quarantines):
        raise TemporalIndexError("HANDOFF_COUNT_MISMATCH", "trailer counts do not match records")
    if trailer.get("eventDigest") != event_hash.hexdigest():
        raise TemporalIndexError("HANDOFF_DIGEST_MISMATCH", "event digest does not match handoff bytes")
    thread_metadata = validate_thread_metadata(header.get(THREAD_METADATA_KEY, {}))
    if record_count < 2:
        raise TemporalIndexError("HANDOFF_INCOMPLETE", "handoff contains no event/trailer body")
    return {"header": header, "trailer": trailer, "events": events, "quarantines": quarantines, "threadMetadata": thread_metadata}


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


@contextmanager
def writer_lock(database_path: Path):
    """Serialize rebuild/incremental writers with SQLite's recoverable lock."""

    lock_path = Path(f"{database_path}.writer-lock.sqlite3")
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(lock_path, timeout=30, isolation_level=None)
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("CREATE TABLE IF NOT EXISTS writer_lock (id INTEGER PRIMARY KEY CHECK(id=1))")
        connection.execute("INSERT OR IGNORE INTO writer_lock(id) VALUES(1)")
        connection.execute("BEGIN IMMEDIATE")
    except sqlite3.DatabaseError as exc:
        if connection is not None:
            connection.close()
        raise TemporalIndexError("INDEX_WRITER_LOCK_TIMEOUT", "temporal index writer lock is unavailable") from exc
    try:
        yield
    finally:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.DatabaseError:
            pass
        connection.close()


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            role TEXT NOT NULL,
            timestamp_utc TEXT NOT NULL,
            timestamp_ms INTEGER NOT NULL,
            text TEXT NOT NULL,
            text_digest TEXT NOT NULL,
            canonical_source_kind TEXT NOT NULL,
            canonical_source_file_digest TEXT NOT NULL,
            canonical_line_number INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS event_sources (
            event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
            source_kind TEXT NOT NULL,
            source_file_digest TEXT NOT NULL,
            line_number INTEGER NOT NULL,
            is_canonical INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(event_id, source_kind, source_file_digest, line_number)
        );
        CREATE TABLE IF NOT EXISTS quarantine (
            quarantine_id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_file_digest TEXT NOT NULL,
            line_number INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            applied_at TEXT NOT NULL,
            status TEXT NOT NULL,
            manifest_digest TEXT,
            event_digest TEXT,
            event_count INTEGER NOT NULL,
            quarantine_count INTEGER NOT NULL,
            error_code TEXT
        );
        CREATE TABLE IF NOT EXISTS thread_metadata (
            thread_id TEXT PRIMARY KEY,
            workspace_label TEXT NOT NULL,
            workspace_hash TEXT,
            archived INTEGER NOT NULL,
            source TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL,
            description TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS events_time_idx ON events(timestamp_ms, event_id);
        CREATE INDEX IF NOT EXISTS events_thread_time_idx ON events(thread_id, timestamp_ms, event_id);
        CREATE INDEX IF NOT EXISTS sources_event_idx ON event_sources(event_id, is_canonical);
        CREATE INDEX IF NOT EXISTS quarantine_thread_idx ON quarantine(thread_id, line_number);
        """
    )
    existing = connection.execute("SELECT value FROM meta WHERE key='schemaVersion'").fetchone()
    existing_version = int(existing[0]) if existing is not None else None
    if existing_version not in {None, LEGACY_SCHEMA_VERSION, SCHEMA_VERSION}:
        raise TemporalIndexError("INDEX_SCHEMA_MISMATCH", f"schema {existing_version} is not supported")
    for key, expected, code in (
        ("contractVersion", CONTRACT, "INDEX_CONTRACT_MISMATCH"),
        ("policyVersion", POLICY, "INDEX_POLICY_MISMATCH"),
    ):
        prior = connection.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if prior is not None and prior[0] != expected:
            raise TemporalIndexError(code, f"{key} {prior[0]} is not supported")
    if existing_version == LEGACY_SCHEMA_VERSION:
        try:
            connection.execute("BEGIN IMMEDIATE")
            set_meta(connection, "schemaVersion", str(SCHEMA_VERSION))
            connection.execute(
                "INSERT OR REPLACE INTO schema_migrations(version,applied_at,description) VALUES(?,?,?)",
                (SCHEMA_VERSION, utc_now(), "add path-free thread workspace metadata and migration ledger"),
            )
            connection.execute("COMMIT")
        except sqlite3.DatabaseError as exc:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.DatabaseError:
                pass
            raise TemporalIndexError("INDEX_MIGRATION_FAILED", "schema v1 could not be upgraded to v2") from exc
    elif existing_version is None:
        connection.execute(
            "INSERT OR REPLACE INTO schema_migrations(version,applied_at,description) VALUES(?,?,?)",
            (SCHEMA_VERSION, utc_now(), "initial temporal index schema with path-free thread workspace metadata"),
        )
    set_meta(connection, "schemaVersion", str(SCHEMA_VERSION))
    set_meta(connection, "contractVersion", CONTRACT)
    set_meta(connection, "policyVersion", POLICY)


def set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def _source_rank(source_kind: str) -> int:
    return 0 if source_kind == "active" else 1


def _canonical_ref(refs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return min(refs, key=lambda ref: (_source_rank(ref["sourceKind"]), ref["sourceFileDigest"], ref["lineNumber"]))


def _apply_handoff(connection: sqlite3.Connection, handoff: dict[str, Any]) -> None:
    events = handoff["events"]
    quarantines = handoff["quarantines"]
    refs_by_event: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        refs_by_event.setdefault(event["eventId"], []).append(event["sourceRef"])
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            """
            CREATE TEMP TABLE incoming_events (
                event_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                role TEXT NOT NULL,
                timestamp_utc TEXT NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                text TEXT NOT NULL,
                text_digest TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TEMP TABLE incoming_sources (
                event_id TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_file_digest TEXT NOT NULL,
                line_number INTEGER NOT NULL,
                PRIMARY KEY(event_id, source_kind, source_file_digest, line_number)
            )
            """
        )
        unique_events = {event["eventId"]: event for event in events}
        for event in unique_events.values():
            connection.execute(
                "INSERT INTO incoming_events VALUES(?,?,?,?,?,?,?)",
                (
                    event["eventId"], event["threadId"], event["role"], event["timestampUtc"],
                    timestamp_ms(event["timestampUtc"]), event["text"], event["textDigest"],
                ),
            )
        for event_id, refs in refs_by_event.items():
            for ref in refs:
                connection.execute(
                    "INSERT OR IGNORE INTO incoming_sources VALUES(?,?,?,?)",
                    (event_id, ref["sourceKind"], ref["sourceFileDigest"], ref["lineNumber"]),
                )
        connection.execute(
            "DELETE FROM event_sources WHERE NOT EXISTS (SELECT 1 FROM incoming_sources incoming WHERE incoming.event_id=event_sources.event_id AND incoming.source_kind=event_sources.source_kind AND incoming.source_file_digest=event_sources.source_file_digest AND incoming.line_number=event_sources.line_number)"
        )
        connection.execute(
            "DELETE FROM events WHERE NOT EXISTS (SELECT 1 FROM incoming_events incoming WHERE incoming.event_id=events.event_id)"
        )
        for event in unique_events.values():
            connection.execute(
                """
                INSERT INTO events(event_id,thread_id,role,timestamp_utc,timestamp_ms,text,text_digest,canonical_source_kind,canonical_source_file_digest,canonical_line_number)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(event_id) DO UPDATE SET
                    thread_id=excluded.thread_id,
                    role=excluded.role,
                    timestamp_utc=excluded.timestamp_utc,
                    timestamp_ms=excluded.timestamp_ms,
                    text=excluded.text,
                    text_digest=excluded.text_digest
                """,
                (
                    event["eventId"], event["threadId"], event["role"], event["timestampUtc"],
                    timestamp_ms(event["timestampUtc"]), event["text"], event["textDigest"],
                    event["sourceRef"]["sourceKind"], event["sourceRef"]["sourceFileDigest"], event["sourceRef"]["lineNumber"],
                ),
            )
        connection.execute(
            """
            INSERT OR IGNORE INTO event_sources(event_id,source_kind,source_file_digest,line_number,is_canonical)
            SELECT event_id,source_kind,source_file_digest,line_number,0 FROM incoming_sources
            """
        )
        for event_id, refs in refs_by_event.items():
            best = _canonical_ref(refs)
            connection.execute("UPDATE event_sources SET is_canonical=0 WHERE event_id=?", (event_id,))
            connection.execute(
                "UPDATE event_sources SET is_canonical=1 WHERE event_id=? AND source_kind=? AND source_file_digest=? AND line_number=?",
                (event_id, best["sourceKind"], best["sourceFileDigest"], best["lineNumber"]),
            )
            connection.execute(
                "UPDATE events SET canonical_source_kind=?, canonical_source_file_digest=?, canonical_line_number=? WHERE event_id=?",
                (best["sourceKind"], best["sourceFileDigest"], best["lineNumber"], event_id),
            )
        connection.execute("DELETE FROM quarantine")
        for record in quarantines:
            ref = record["sourceRef"]
            connection.execute(
                "INSERT INTO quarantine(thread_id,reason,source_kind,source_file_digest,line_number) VALUES(?,?,?,?,?)",
                (record["threadId"], record["reason"], ref["sourceKind"], ref["sourceFileDigest"], ref["lineNumber"]),
            )
        connection.execute("DELETE FROM thread_metadata")
        for thread_id, metadata in (handoff.get("threadMetadata") or {}).items():
            connection.execute(
                "INSERT INTO thread_metadata(thread_id,workspace_label,workspace_hash,archived,source) VALUES(?,?,?,?,?)",
                (
                    thread_id,
                    metadata["workspaceLabel"],
                    metadata.get("workspaceHash"),
                    int(bool(metadata.get("archived", False))),
                    metadata.get("source", "unknown"),
                ),
            )
        header = handoff["header"]
        trailer = handoff["trailer"]
        set_meta(connection, "manifestDigest", str(header.get("manifestDigest") or ""))
        set_meta(connection, "eventDigest", str(trailer["eventDigest"]))
        set_meta(connection, "eventCount", str(len(unique_events)))
        set_meta(connection, "quarantineCount", str(len(quarantines)))
        set_meta(connection, THREAD_METADATA_KEY, json.dumps(handoff.get("threadMetadata") or {}, sort_keys=True, separators=(",", ":")))
        set_meta(connection, "lastAppliedAt", utc_now())
        connection.execute(
            "INSERT INTO runs(applied_at,status,manifest_digest,event_digest,event_count,quarantine_count) VALUES(?,?,?,?,?,?)",
            (utc_now(), "complete", header.get("manifestDigest"), trailer["eventDigest"], len(unique_events), len(quarantines)),
        )
        connection.execute("DROP TABLE incoming_sources")
        connection.execute("DROP TABLE incoming_events")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def verify_connection(connection: sqlite3.Connection) -> dict[str, Any]:
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.DatabaseError as exc:
        raise TemporalIndexError("INDEX_CORRUPT", str(exc)) from exc
    if integrity != "ok":
        raise TemporalIndexError("INDEX_CORRUPT", str(integrity))
    row = connection.execute("SELECT value FROM meta WHERE key='schemaVersion'").fetchone()
    if row is None or int(row[0]) != SCHEMA_VERSION:
        raise TemporalIndexError("INDEX_SCHEMA_MISMATCH", "schema metadata is missing or unsupported")
    for key, expected, code in (
        ("contractVersion", CONTRACT, "INDEX_CONTRACT_MISMATCH"),
        ("policyVersion", POLICY, "INDEX_POLICY_MISMATCH"),
    ):
        value = connection.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if value is None or value[0] != expected:
            raise TemporalIndexError(code, f"{key} is missing or unsupported")
    migration_table = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if migration_table is None or connection.execute(
        "SELECT version FROM schema_migrations WHERE version=?", (SCHEMA_VERSION,)
    ).fetchone() is None:
        raise TemporalIndexError("INDEX_SCHEMA_MISMATCH", "schema migration ledger is missing or incomplete")
    counts = connection.execute("SELECT (SELECT COUNT(*) FROM events), (SELECT COUNT(*) FROM event_sources), (SELECT COUNT(*) FROM quarantine)").fetchone()
    thread_metadata = _metadata_from_connection(connection)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "contractVersion": connection.execute("SELECT value FROM meta WHERE key='contractVersion'").fetchone()[0],
        "policyVersion": connection.execute("SELECT value FROM meta WHERE key='policyVersion'").fetchone()[0],
        "eventCount": counts[0],
        "sourceReferenceCount": counts[1],
        "quarantineCount": counts[2],
        "threadMetadataCount": len(thread_metadata),
        "lastAppliedAt": (connection.execute("SELECT value FROM meta WHERE key='lastAppliedAt'").fetchone() or [None])[0],
        "manifestDigest": (connection.execute("SELECT value FROM meta WHERE key='manifestDigest'").fetchone() or [None])[0],
        "eventDigest": (connection.execute("SELECT value FROM meta WHERE key='eventDigest'").fetchone() or [None])[0],
    }


def verify_database(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise TemporalIndexError("INDEX_MISSING", "database does not exist")
    try:
        connection = connect(path)
        try:
            return verify_connection(connection)
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise TemporalIndexError("INDEX_CORRUPT", str(exc)) from exc


def _backup_existing(path: Path, suffix: str = ".previous") -> Path | None:
    if not path.exists():
        return None
    backup = Path(f"{path}{suffix}")
    shutil.copy2(path, backup)
    return backup


def _stored_schema_version(path: Path) -> int | None:
    """Read only the schema marker so the supported v1 -> v2 migration can run."""
    try:
        connection = sqlite3.connect(path, timeout=5)
        try:
            row = connection.execute("SELECT value FROM meta WHERE key='schemaVersion'").fetchone()
            return int(row[0]) if row else None
        finally:
            connection.close()
    except (sqlite3.DatabaseError, ValueError) as exc:
        raise TemporalIndexError("INDEX_CORRUPT", "schema marker could not be read") from exc


def build_index(handoff_path: Path, database_path: Path, rebuild: bool = False) -> dict[str, Any]:
    handoff = load_handoff(handoff_path)
    database_path = database_path.resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with writer_lock(database_path):
        if database_path.exists() and not rebuild:
            try:
                current = verify_database(database_path)
            except TemporalIndexError as exc:
                if exc.code != "INDEX_SCHEMA_MISMATCH" or _stored_schema_version(database_path) != LEGACY_SCHEMA_VERSION:
                    raise
                connection = connect(database_path)
                try:
                    initialize_schema(connection)
                finally:
                    connection.close()
                current = verify_database(database_path)
            if current.get("eventDigest") == handoff["trailer"]["eventDigest"] and current.get("manifestDigest") == handoff["header"].get("manifestDigest"):
                return {**current, "changed": False, "noOp": True}
            try:
                _backup_existing(database_path)
            except OSError as exc:
                raise TemporalIndexError("INDEX_BACKUP_FAILED", "last-good index could not be protected") from exc
            connection = connect(database_path)
            try:
                try:
                    initialize_schema(connection)
                    _apply_handoff(connection, handoff)
                    result = verify_connection(connection)
                except TemporalIndexError:
                    raise
                except sqlite3.DatabaseError as exc:
                    raise TemporalIndexError("INDEX_BUILD_FAILED", "incremental index update failed") from exc
            finally:
                connection.close()
            return {**result, "changed": True, "noOp": False}

        temporary = Path(f"{database_path}.rebuild-{os.getpid()}")
        try:
            if temporary.exists():
                temporary.unlink()
            connection = connect(temporary)
            try:
                initialize_schema(connection)
                _apply_handoff(connection, handoff)
                result = verify_connection(connection)
            finally:
                connection.close()
            _backup_existing(database_path, ".pre-rebuild")
            os.replace(temporary, database_path)
            return {**result, "changed": True, "noOp": False, "rebuilt": True}
        except TemporalIndexError:
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise TemporalIndexError("INDEX_BUILD_FAILED", "temporary index promotion failed") from exc
        finally:
            if temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass


def query_thread_metadata(path: Path) -> dict[str, dict[str, Any]]:
    """Return non-secret workspace metadata for indexed threads."""
    connection = connect(path)
    try:
        return _metadata_from_connection(connection)
    finally:
        connection.close()


def query_thread_ids_by_project(path: Path, project: str) -> list[str]:
    """Resolve an exact workspace label or hash to canonical thread IDs."""
    needle = str(project or "").strip().casefold()
    if not needle:
        raise TemporalIndexError("INVALID_PROJECT", "project filter must not be empty")
    metadata = query_thread_metadata(path)
    if not metadata:
        raise TemporalIndexError("PROJECT_METADATA_UNAVAILABLE", "index has no workspace metadata; refresh the temporal index first")
    matches = [
        thread_id
        for thread_id, value in metadata.items()
        if needle in {str(value.get("workspaceLabel") or "").casefold(), str(value.get("workspaceHash") or "").casefold()}
    ]
    return sorted(matches)


def query_events(path: Path, start: str, end: str, thread_ids: list[str] | None = None) -> list[dict[str, Any]]:
    start_ms = timestamp_ms(start)
    end_ms = timestamp_ms(end)
    if end_ms <= start_ms:
        raise TemporalIndexError("INVALID_TIME_RANGE", "end must be after start")
    connection = connect(path)
    try:
        sql = "SELECT event_id,thread_id,role,timestamp_utc,text,text_digest,canonical_source_kind,canonical_source_file_digest,canonical_line_number FROM events WHERE timestamp_ms>=? AND timestamp_ms<?"
        parameters: list[Any] = [start_ms, end_ms]
        if thread_ids:
            placeholders = ",".join("?" for _ in thread_ids)
            sql += f" AND thread_id IN ({placeholders})"
            parameters.extend(thread_ids)
        sql += " ORDER BY timestamp_ms,thread_id,event_id"
        rows = connection.execute(sql, parameters).fetchall()
        return [
            {
                "eventId": row[0], "threadId": row[1], "role": row[2], "timestampUtc": row[3],
                "text": row[4], "textDigest": row[5],
                "sourceRef": {"sourceKind": row[6], "sourceFileDigest": row[7], "lineNumber": row[8]},
            }
            for row in rows
        ]
    finally:
        connection.close()


def query_thread_events(path: Path, thread_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Return canonical history for the requested threads.

    Context packing uses this read-only view to keep activity boundaries stable
    when a requested period starts or ends in the middle of an activity. The
    index remains the only SQL boundary; callers still decide which rows are
    inside the requested half-open period.
    """

    connection = connect(path)
    try:
        sql = "SELECT event_id,thread_id,role,timestamp_utc,text,text_digest,canonical_source_kind,canonical_source_file_digest,canonical_line_number FROM events"
        parameters: list[Any] = []
        if thread_ids:
            placeholders = ",".join("?" for _ in thread_ids)
            sql += f" WHERE thread_id IN ({placeholders})"
            parameters.extend(thread_ids)
        sql += " ORDER BY timestamp_ms,thread_id,event_id"
        rows = connection.execute(sql, parameters).fetchall()
        return [
            {
                "eventId": row[0], "threadId": row[1], "role": row[2], "timestampUtc": row[3],
                "text": row[4], "textDigest": row[5],
                "sourceRef": {"sourceKind": row[6], "sourceFileDigest": row[7], "lineNumber": row[8]},
            }
            for row in rows
        ]
    finally:
        connection.close()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or query the local temporal SQLite index.")
    parser.add_argument("--handoff", type=Path)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--thread", action="append", dest="threads")
    parser.add_argument("--all-threads", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.handoff:
            result = build_index(args.handoff.resolve(), args.db.resolve(), rebuild=args.rebuild)
        elif args.verify:
            result = verify_database(args.db.resolve())
        elif args.start and args.end:
            result = {"status": "ok", "events": query_events(args.db.resolve(), args.start, args.end, args.threads)}
        elif args.all_threads:
            result = {"status": "ok", "events": query_thread_events(args.db.resolve(), args.threads)}
        else:
            raise TemporalIndexError("USAGE", "provide --handoff, --verify, or --start and --end")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except TemporalIndexError as exc:
        print(json.dumps({"status": "error", "code": exc.code, "message": str(exc)}, indent=2), file=sys.stderr)
        return 1
    except sqlite3.DatabaseError as exc:
        print(json.dumps({"status": "error", "code": "INDEX_CORRUPT", "message": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
