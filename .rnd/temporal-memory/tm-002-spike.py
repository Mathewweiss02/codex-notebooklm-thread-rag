"""TM-002 storage-boundary spike.

This is an R&D harness, not product code. It measures stable stdlib SQLite
storage with three content-placement choices while keeping the event contract
language-neutral. All data is synthetic and generated under a temporary root.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCALES = (1_000, 5_000, 20_000)
MODES = ("text_in_db", "metadata_sidecar", "content_addressed")


def synthetic_rows(count: int) -> list[dict[str, object]]:
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    for index in range(count):
        timestamp = start + timedelta(seconds=index * 71)
        text = f"synthetic activity cluster {index % 100} event {index} with stable evidence payload"
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        rows.append(
            {
                "event_id": f"event-{index:08d}",
                "thread_id": f"thread-{index % 37:03d}",
                "role": "user" if index % 2 == 0 else "assistant",
                "timestamp_ms": int(timestamp.timestamp() * 1000),
                "timestamp_utc": timestamp.isoformat().replace("+00:00", "Z"),
                "text": text,
                "content_digest": digest,
            }
        )
    return rows


def size_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def prepare_content(root: Path, rows: list[dict[str, object]], mode: str) -> None:
    if mode == "text_in_db":
        return
    if mode == "metadata_sidecar":
        sidecar = root / "content.ndjson"
        with sidecar.open("wb") as handle:
            for row in rows:
                payload = (str(row["text"]) + "\n").encode("utf-8")
                row["content_offset"] = handle.tell()
                row["content_length"] = len(payload)
                handle.write(payload)
        return
    if mode == "content_addressed":
        blob_root = root / "blobs"
        blob_root.mkdir()
        paths: dict[str, Path] = {}
        for row in rows:
            digest = str(row["content_digest"])
            path = paths.get(digest)
            if path is None:
                path = blob_root / f"{digest}.txt"
                path.write_text(str(row["text"]), encoding="utf-8")
                paths[digest] = path
            row["blob_name"] = path.name
        return
    raise ValueError(f"unknown content mode: {mode}")


def build_and_measure(root: Path, rows: list[dict[str, object]], mode: str) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    prepare_content(root, rows, mode)
    database_path = root / "events.sqlite3"
    started = time.perf_counter()
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    columns = [
        "event_id TEXT PRIMARY KEY",
        "thread_id TEXT NOT NULL",
        "role TEXT NOT NULL",
        "timestamp_ms INTEGER NOT NULL",
        "timestamp_utc TEXT NOT NULL",
        "content_digest TEXT NOT NULL",
    ]
    if mode == "text_in_db":
        columns.append("text TEXT NOT NULL")
    elif mode == "metadata_sidecar":
        columns.extend(["content_offset INTEGER NOT NULL", "content_length INTEGER NOT NULL"])
    else:
        columns.append("blob_name TEXT NOT NULL")
    connection.execute(f"CREATE TABLE events ({', '.join(columns)})")
    connection.execute("CREATE INDEX events_time_idx ON events(timestamp_ms, event_id)")
    connection.execute("CREATE INDEX events_thread_time_idx ON events(thread_id, timestamp_ms, event_id)")
    if mode == "text_in_db":
        insert_columns = "event_id,thread_id,role,timestamp_ms,timestamp_utc,content_digest,text"
        values = [
            (row["event_id"], row["thread_id"], row["role"], row["timestamp_ms"], row["timestamp_utc"], row["content_digest"], row["text"])
            for row in rows
        ]
    elif mode == "metadata_sidecar":
        insert_columns = "event_id,thread_id,role,timestamp_ms,timestamp_utc,content_digest,content_offset,content_length"
        values = [
            (row["event_id"], row["thread_id"], row["role"], row["timestamp_ms"], row["timestamp_utc"], row["content_digest"], row["content_offset"], row["content_length"])
            for row in rows
        ]
    else:
        insert_columns = "event_id,thread_id,role,timestamp_ms,timestamp_utc,content_digest,blob_name"
        values = [
            (row["event_id"], row["thread_id"], row["role"], row["timestamp_ms"], row["timestamp_utc"], row["content_digest"], row["blob_name"])
            for row in rows
        ]
    placeholders = ",".join("?" for _ in insert_columns.split(","))
    connection.executemany(f"INSERT INTO events ({insert_columns}) VALUES ({placeholders})", values)
    connection.commit()
    build_ms = (time.perf_counter() - started) * 1000

    query_started = time.perf_counter()
    start_ms = int(rows[len(rows) // 3]["timestamp_ms"])
    end_ms = int(rows[(len(rows) * 2) // 3]["timestamp_ms"])
    selected = connection.execute(
        "SELECT * FROM events WHERE timestamp_ms >= ? AND timestamp_ms < ? ORDER BY timestamp_ms,event_id",
        (start_ms, end_ms),
    ).fetchall()
    query_ms = (time.perf_counter() - query_started) * 1000

    context_started = time.perf_counter()
    context_count = min(100, len(selected))
    if mode == "text_in_db":
        text_index = len(columns) - 1
        _ = [str(row[text_index]) for row in selected[:context_count]]
    elif mode == "metadata_sidecar":
        with (root / "content.ndjson").open("rb") as handle:
            offset_index = len(columns) - 2
            length_index = len(columns) - 1
            for row in selected[:context_count]:
                handle.seek(int(row[offset_index]))
                _ = handle.read(int(row[length_index]))
    else:
        blob_index = len(columns) - 1
        for row in selected[:context_count]:
            _ = (root / "blobs" / str(row[blob_index])).read_text(encoding="utf-8")
    context_ms = (time.perf_counter() - context_started) * 1000
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    connection.close()
    return {
        "mode": mode,
        "events": len(rows),
        "selected": len(selected),
        "contextSample": context_count,
        "buildMs": round(build_ms, 3),
        "queryMs": round(query_ms, 3),
        "contextMs": round(context_ms, 3),
        "bytes": size_bytes(root),
    }


def main() -> int:
    runs: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="tm002-spike-") as temporary:
        root = Path(temporary)
        for scale in SCALES:
            for mode in MODES:
                runs.append(build_and_measure(root / f"{mode}-{scale}", synthetic_rows(scale), mode))
    payload = {
        "experiment": "TM-002",
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "scales": SCALES,
        "modes": MODES,
        "runs": runs,
        "note": "Synthetic benchmark only; no private corpus content or identifiers.",
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
