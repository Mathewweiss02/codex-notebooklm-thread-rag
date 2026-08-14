# TM-002 Run Packet

## Mission

Select a stable local index engine and content-placement boundary that preserve the existing Node visibility/redaction contract, support atomic rebuilds on Windows, and keep temporal context assembly fast.

## Chosen comparison

- ID: `TM-002`
- Title: Run ADR spikes for index engine and indexed-content boundary
- Why now: TM-001 fixed the event and provenance contract but intentionally left the storage boundary empirical; TM-003 and TM-004 cannot be implemented cleanly until this choice is made.

## Hypothesis

The best maintainable path is to reuse the existing Node event parser, hand off a versioned canonical-event stream, and maintain a local SQLite-derived index with sanitized text available for context assembly.

## Variables

- Engine: Node experimental `node:sqlite` versus pinned Python 3.12 stdlib `sqlite3`.
- Content placement: sanitized text in SQLite, metadata plus one sidecar content file, or content-addressed blobs.
- Corpus scale: 1,000, 5,000, and 20,000 synthetic events.

## Metrics or evidence

- Runtime stability and dependency status.
- Build, indexed-period query, and 100-message context-read wall time.
- Derived-state disk footprint.
- Parser/redaction duplication risk and atomic-rebuild ergonomics.

## Method

1. Inspect available runtime support without changing installations.
2. Run the synthetic Python 3.12 SQLite spike for all content modes and scales.
3. Run a small Node `node:sqlite` comparison, recording its experimental status.
4. Select the option that satisfies correctness, maintainability, Windows support, and measured latency together.
5. Preserve the decision and result under `.rnd/temporal-memory`; do not add product code in the comparison lane.

## Stop condition

Reject any option that duplicates visibility/redaction semantics, cannot retain a last-known-good state, or relies on an unpinned experimental runtime primitive as a production foundation.

## Recommended next lane

`implementation` after the ADR result: build the canonical extractor/index seam and prove exact oracle parity.
