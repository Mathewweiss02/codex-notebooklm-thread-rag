# TM-000 Run Packet

## Mission

Freeze the current repository and runtime behavior, then establish an independent synthetic temporal oracle before any temporal-index or query-routing feature work begins.

## Chosen measurement

- ID: `TM-000`
- Title: Freeze current baseline and private temporal oracle fixtures
- Why now: every later correctness, performance, and NotebookLM decision depends on knowing what the current system does and having a completeness reference that is not produced by the implementation under test.

## Hypothesis

The current repository can be reproduced from a clean invocation, and a small synthetic corpus can expose the temporal invariants required for exact local selection: message-level timestamps, half-open ranges, midnight boundaries, DST-short and DST-long days, visible-role filtering, invalid timestamp exclusion, and active/archive deduplication.

## Variable

- Observed baseline: repository revision, installed runtimes, test suite, app-server inventory, registry role shape, and local semantic-search latency.
- Controlled fixture cases: UTC instants, local calendar boundaries, roles, source lineage, duplicate records, and malformed/missing timestamps.

## Metric or evidence

- Current suite exit status and per-surface test counts.
- Aggregate visible-task count and salted-free corpus identity fingerprint.
- Local search wall time for three identical read-only runs.
- Oracle case pass count and deterministic result digest.
- No real task content, credentials, source IDs, or account identifiers in committed artifacts.

## Method

1. Run `tests/run_all.ps1` using the pinned NotebookLM runtime Python.
2. Record only aggregate environment and app-server inventory values.
3. Run the synthetic oracle against `.rnd/temporal-memory/fixtures/oracle-fixtures.json`.
4. Preserve the run packet, result surface, baseline aggregate, and fixture definition under this `.rnd` workspace.
5. Do not modify product/runtime/scheduler/NotebookLM state during this measurement.

## Stop condition

Do not start temporal feature code until the current suite and the oracle reproduce on rerun, and no baseline discrepancy is unexplained.

## Recommended next lane

`planning` — approve the event, time-range, context-pack, and verification contracts before implementation.
