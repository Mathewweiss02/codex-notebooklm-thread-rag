# TM-001 Contract Packet — Temporal Memory and NotebookLM Synthesis

Status: approved for implementation spikes

Approved: 2026-08-14

Machine-readable source: `contracts-v1.json`

## Mission contract

### Objective

Make period-based memory queries exhaustive and deterministic locally, then use NotebookLM only for bounded, source-scoped synthesis whose claims are checked against local evidence.

### Desired outcome

A fresh Codex task can ask for yesterday, a date, last week, a time range, or a topic within a period and receive an answer that discloses its resolved range, coverage, mode, omissions, provenance, verification state, and latency.

### Non-goals

- Replacing Codex's canonical session storage.
- Treating NotebookLM prose as canonical truth.
- Resetting persistent CLI chat conversations.
- Duplicating every transcript into daily and weekly NotebookLM sources by default.
- Promising 50-way concurrency or making it a default.
- Hiding unsupported timestamps by assigning them to a guessed day.

### Success signals

- Exact period selection equals the independent oracle for every supported case.
- All accepted remote claims map to current local evidence.
- Local mode remains useful during NotebookLM outage/auth/rate-limit failure.
- State updates are incremental, atomic, rebuildable, and observable.
- Parallelism is increased only after isolation and quality gates pass.

### Current biggest unknown

The safe and useful NotebookLM query topology is still unproven. It remains a later experiment, not a contract assumption.

## Event contract

The canonical event is a visible user or assistant message. Its temporal membership comes from the message timestamp, never the thread creation or update time. Events without a valid timestamp are quarantined and reported; they are never silently assigned to a period.

The stable identity is `sha256(threadId + NUL + role + NUL + timestampUtc + NUL + sanitizedText)`. Active/archive copies with the same identity collapse to one canonical event while retaining lineage references. Forked threads remain separate because `threadId` is part of the identity. Source file paths stay inside local authority; reports use a file digest and line number.

The existing visibility and redaction policy remains the single boundary. Tool payloads, reasoning, developer records, compaction summaries, attachments, and other non-visible records do not enter the temporal corpus.

## Time-range contract

All stored instants are UTC. Every query resolves once against an explicit IANA time zone and uses a half-open range `[startUtc,endUtc)`. This prevents midnight double inclusion and makes adjacent periods composable.

- `today` means local midnight through the captured command time.
- `yesterday` means the previous local calendar day.
- `past N hours/days` means a rolling duration ending at the captured command time.
- `last week` means the previous Monday–Sunday calendar week by default.
- `week to date` means the current week start through the captured command time.
- An explicit date means the complete local calendar day.
- An explicit timestamp without an offset is rejected unless a time zone is supplied.
- An ambiguous local timestamp is rejected unless its offset disambiguates it.
- A nonexistent local timestamp is rejected.
- A future range returns an honest empty result with the resolved range.

Every response includes the original expression, time zone, UTC bounds, boundary rule, duration, and captured-now value.

## Context-pack contract

Selection is exhaustive before semantic ranking. The pack hierarchy is:

`period → local day → activity segment → message evidence`

Messages sort deterministically by UTC timestamp, thread ID, and event ID. Brief, standard, and deep budgets may compress presentation, but they must expose canonical count, included count, omitted count, segment count, and drill-down handles. The starting budgets and allocation policy are recorded in `context-pack-policy-v1.json`; omissions are never silent. A summary claim without provenance is not accepted as factual evidence. TM-006 selected `activity-segmentation-v1`: thread-local ordering with a new segment only when the gap is strictly greater than 60 minutes; local midnight does not split a segment. The policy is recorded in `segmentation-policy-v1.json`.

## NotebookLM and verification contract

Remote asks may use only current, ready, locally mapped source parts. A missing, stale, extra, or mismatched source blocks remote synthesis and returns a local/degraded result. Persistent chat notebooks are never selected by automation. Disposable retrieval conversations can be reset only under their explicit retrieval policy.

The default remote concurrency is one. The permitted research ramp is 1 → 2 → 4 → 8 → 16, with 32/50 requiring a separate value-and-safety decision. Shared mutable conversations serialize or reject concurrent asks. A faster result that introduces cross-talk, citation misassignment, rate-limit instability, or orphaned work is a failure.

Every accepted remote claim must map to local event evidence and a current source mapping. Wrong-day, wrong-thread, stale-source, and unverifiable citations are rejected. Remote outage, auth failure, or timeout falls back deterministically to local mode; it never becomes an empty-success result.

## Result and failure contract

The result status is one of `ok`, `empty`, `degraded`, `abstained`, or `error`. Every result exposes mode, resolved range, coverage, provenance, verification, latency, retries, and omissions. Errors are never represented as empty periods, and an old success timestamp is not proof of a current successful run.

The index retains the last known-good committed state until a new state is atomically committed and verified. Corruption, schema mismatch, source drift, unsafe conversation state, auth failure, rate limiting, cancellation, and budget exhaustion have explicit machine-readable error codes and fail-closed behavior.

## Approval and deferred decisions

This packet approves the contracts and invariants needed to begin the two ADR spikes. It deliberately leaves the following empirical choices open:

- SQLite/index boundary and language split (`TM-002`).
- Whether sanitized text is stored in the index or read from canonical files (`TM-002`).
- Context-budget allocation (`TM-007`).
- Context-budget allocation (`TM-007`).
- NotebookLM conversation/replica topology (`PQ-001` through `PQ-004`).
