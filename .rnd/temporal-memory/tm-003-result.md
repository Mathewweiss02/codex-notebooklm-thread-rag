# TM-003 Result

## What was built

- Added `scripts/thread_temporal_extract.mjs`, which reuses the existing Node visibility/redaction parser and emits an atomic `temporal-event-v1` NDJSON handoff.
- Added explicit event IDs, normalized millisecond UTC timestamps, text digests, source-file digests, source kind, and line provenance.
- Added quarantine records for missing and invalid timestamps.
- Added source-change detection, visible-overflow failure, UTF-8 BOM tolerance for Windows manifests, and cleanup of uncommitted temporary handoffs.
- Added an independent Python slow oracle under `.rnd/temporal-memory/tm-003-oracle.py`; it does not import the production parser.
- Added four extractor regression tests covering success/lineage identity, missing-source atomic failure, visible overflow, and BOM input.

## Evidence

- Synthetic fixture: 10 emitted lineage records, 9 canonical events after active/archive collapse, and 2 quarantined records.
- Independent oracle parity: passed on three consecutive runs.
- Current signature digest after the lineage-fixture correction: `2303e949c9fafd4186453c0bdfbebfd40e7b045c2e878ecef1267aead5c31250`.
- Extractor regression tests: 4/4 passed.
- No real conversation content, credentials, or raw paths were written to repository artifacts.

## Result

The TM-003 hypothesis is strengthened. The existing projection parser can be extended at a narrow seam without duplicating visibility/redaction logic, and the handoff can be verified independently before indexing.

## Limitations

- The parity corpus is synthetic; a path-bearing, read-only real-corpus manifest is still required before release certification.
- Active/archive canonical selection across the full index belongs to TM-004; the extractor preserves lineage records and stable IDs for that stage.
- Process handoff throughput and full-corpus rebuild behavior remain unmeasured.

## Next move

Advance `TM-003` to done and implement `TM-004`: crash-safe SQLite index state, active/archive canonicalization, migrations, integrity checks, and rebuild/rollback behavior.
