# TM-004 Result

## What was built

- Added `scripts/thread_temporal_index.py` using the pinned Python runtime's stdlib SQLite.
- Added versioned schema metadata, event/source-lineage/quarantine/run tables, timestamp/thread indexes, and sanitized text storage.
- Added producer contract validation, event-ID/text-digest validation, handoff digest validation, active/archive canonical selection, stale-event removal, and half-open time queries.
- Added true no-op detection for unchanged handoffs.
- Added transactional incremental updates with a last-known-good database, `.previous` backup, corruption detection, unsupported-schema fail-closed behavior, and explicit temporary rebuild plus atomic replacement.
- Added three focused test groups, including lineage collapse, no-op/update, bad-handoff retention, corruption recovery, and schema mismatch recovery.

## Evidence

- Full suite passed: 26 Node tests and 63 Python tests.
- Fixture end-to-end: 10 emitted lineage records -> 9 canonical events, 10 source references, 2 quarantined records, `PRAGMA integrity_check=ok`.
- Half-open query selected the exact start-boundary event and excluded the exact end-boundary event.
- Bad handoff validation left the previous database unchanged.
- Corrupt and unsupported-schema databases failed closed until explicit rebuild; rebuild restored a verified schema-1 database.

## Result

The TM-004 hypothesis is strengthened. The temporal index is now a local, independently verifiable derived state with transactional update and rebuild paths. It is not yet release-certified: process-kill injection, disk-full behavior, migration history across released versions, real-corpus replay, and scale profiling remain open gates.

## Next move

Advance `TM-004` to done for the current schema and begin `TM-005`: deterministic DST-safe temporal expression resolution with explicit timezone, phrase, ambiguity, and future-range contracts.
