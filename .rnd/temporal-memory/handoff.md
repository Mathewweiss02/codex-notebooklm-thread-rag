# Temporal Memory Handoff

## Current lane

Validation: REL-002 soak and rollback evidence

## Recommended next lane

Run the seven-day or reset fourteen-day soak and rollback rehearsal across the
current temporal/index/doctor/scheduler paths. Keep the local CLI/index as
authority, preserve the persistent chat notebook, and reject unverified remote
claims.

## Why now

The baseline, contracts, ADR evidence, synthetic extractor/oracle parity, crash-safe SQLite index, and DST-safe resolver are reproducible and explicit. The selected boundary is Node parser → versioned redacted event handoff → pinned Python SQLite, with sanitized text in the derived index.

## What must be true first

- The extractor emits only `temporal-event-v1` records under the existing visibility/redaction policy.
- Independent oracle parity is exact on synthetic fixtures before real corpus replay.
- The handoff is bounded, hashed, and atomic; no partial index commit is accepted.
- Index writers now serialize through a recoverable SQLite sidecar lock; readers
  continue to see only committed state.
- Refresh promotion also uses a recoverable SQLite overlap lock around the
  staged handoff/index pair, so concurrent refreshes cannot reorder a valid
  handoff and index from different generations.
- The indexer preserves a last-known-good state and has a rollback path.
- Schema version 1 migrates in place to version 2 with a migration ledger;
  mismatched or unsupported versions still fail closed. The paired rollback
  rehearsal verifies both derived artifacts and does not touch canonical state.
- Active/archive lineage canonicalization is deterministic and does not merge forked thread IDs.
- Corruption, migrations, disk-full, and process-kill tests pass before the index is promoted.
- Natural-language period resolution is explicit, timezone-aware, half-open, and tested across DST and calendar boundaries.
- `activity-segmentation-v1` is now selected by TM-006: thread-local, strict `gap > 60 minutes`, no midnight-only split.
- `temporal-context-pack-v1` is implemented and tested with complete canonical selection, included/omitted counts, activity boundaries, provenance, and drill-down handles.
- The CLI must expose local-only `recap`, `when`, `find`, `compare`, and `context` flows with machine-readable errors and no NotebookLM dependency for exact temporal questions.
- `recap`, `context`, `find`, and `compare` support an exact path-free project
  filter. Context signals are conservative heuristic annotations only; every
  signal points to included event evidence and reports its provenance.
- The installed skill must route broad date/time questions to `thread_temporal_cli.py`, disclose index/bootstrap diagnostics, and never silently fall back to semantic-only search for exhaustive period requests.
- The source mapper must accept only current ready parts from the selected retrieval config, prove thread identity/lineage, and degrade locally on missing or stale mapping.
- NLM-002 completed a sequential development comparison: 4/4 disposable retrieval calls succeeded, 4/4 citation scopes were valid, and remote synthesis averaged approximately 43.5 seconds versus approximately 0.2 seconds for local selection.
- ADR-004 now makes local temporal selection authoritative and NotebookLM optional synthesis only after complete local coverage and current source mapping. NLM-003 must verify claim-to-event factual alignment before accepting remote content.
- NLM-003 completed the verifier gate: 4/4 live transports succeeded but 0/4 answers were promoted because answer-linked citation passages were not locally matchable. The local fallback is the correct current behavior.
- NLM-010 through NLM-013 now inject remote outage, expired-auth, HTTP 429/503,
  and timeout failures and verify a locally ranked fallback without counting
  it as remote retrieval quality.
- VAL-001 completed with 19/19 development and 10/10 holdout cases. The current holdout is local and digest-sealed, not cryptographically hidden; final release must relocate it outside the repository.
- PQ-001 completed its structural gate: 7/7 tests passed, 16 cases produced
  30 deterministic pack plans across sizes 1/2/4/8, and repeated plan/suite
  digests matched. No live quality or concurrency claim follows from that
  offline result.
- PQ-002 rejected same-notebook `--new` fan-out: the pinned CLI deletes the
  current server-side conversation before asking, and explicit conversation IDs
  only resume already-known conversations. The configured CLI is v0.8.0; a
  separate v0.6.0 executable appears earlier on PATH.
- PQ-003 modeled pool sizes 1/2/4/8 with 147 source parts, a 300-source limit,
  a 60-source reserve, and a 500-notebook limit. Every modeled replica retains
  93 steady source slots; pool size 8 would require 1,176 aggregate source
  copies. No live replicas were created.
- ADR-005 accepted local-first plus optional sequential source-scoped synthesis;
  packed mode is experimental, same-notebook fan-out is rejected, and replicas
  require explicit approval.
- PQ-005 passed 8/8 executor tests and a real executor-integrated NLM-002 rerun:
  4/4 remote transports and 4/4 source scopes were valid, while 0/4 claims
  were promoted by the verifier. No concurrency increase is justified by that
  result.
- PERF-001, RES-001, SEC-001, and OPS-001 passed their current modeled gates.
  The local path measured roughly 202 ms P50 standard context and roughly 203
  ms P50 deep context; the remaining release work is shadow/canary/soak plus
  the gated replica decision.
- REL-001 passed after the first shadow replay exposed and fixed a stale
  temporal handoff integration. The retrieval runner now snapshots canonical
  projection sources, validates a temporary index, and promotes only matching
  handoff/index digests. The live canary completed all six runner steps with
  144 threads, 146 current source parts, 16,058 temporal events, and zero
  quarantines.
- Latest post-enrollment validation refresh completed all six retrieval-runner
  steps with 145 projected threads, 147 current source parts, 16,175 temporal
  events, zero quarantines, matching handoff/index digests, and both
  retrieval (40/40) and persistent-chat (27/27) doctors passing. Source and
  installed script parity is exact at 56/56 files. The full repository gate is
  now 43 Node and 148 Python tests plus operational integrations.
- A scheduled run using an older installed skill briefly reverted the live
  derived index to schema v1 after a source refresh. Installing the current
  skill and rerunning the refresh recovered the state to schema v2 with 145
  metadata records. This validates the committed-revision/install-parity gate
  as release-critical rather than cosmetic.
- The aggregate live packed experiment passed hybrid expectation at pack sizes
  1, 2, and 4 on four questions each, but pack size 8 passed only 7/8. Keep
  packing experimental and do not claim a certified production pack size.

## What would send the work back into research

- Any parser or redaction duplication.
- An unexplained oracle mismatch.
- An index design that needs NotebookLM state to answer local temporal questions.
- A content-storage choice that makes provenance, redaction changes, or secure cleanup ambiguous.
