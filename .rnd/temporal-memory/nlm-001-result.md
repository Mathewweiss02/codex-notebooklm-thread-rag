# NLM-001 Result

## Implementation

- Added `notebooklm_temporal_source_map.py` as a read-only source-scope mapper.
- It validates retrieval role, disposable conversation policy, shared
  redaction policy, current revision, part readiness, local projected-file
  digest, unique source/title ownership, and selected-thread scope.
- It can perform an optional read-only `notebooklm source list --json` check and
  reports missing, mismatched, or bad-status sources without exposing raw CLI
  output.
- It supports context-pack input, explicit thread IDs, `--all`, and `--strict`.

## Fixture verification

- Current ready part maps successfully.
- Missing thread returns `degraded` with `THREAD_NOT_ENROLLED`.
- Local projection digest drift returns `degraded` with `SOURCE_DRIFT`.
- Chat-role config fails closed with `NOTEBOOK_ROLE_UNSAFE`.

## Live verification

Read-only current retrieval mapping on 2026-08-14:

- Requested threads: 140.
- Mapped threads: 140.
- Current parts: 142.
- Local mapping problems: 0.
- Live source matches: 142.
- Live missing: 0.
- Live title mismatches: 0.
- Live bad-status sources: 0.
- Live verification status: `ok`.
- Persistent `chat` config: excluded by role filter.

## Decision

Accept `temporal-source-map-v1` as the only source scope allowed for later
NotebookLM temporal synthesis. A temporal query may proceed remotely only when
the mapper returns `status=ok`; otherwise the local context pack remains the
truthful fallback.

## Limitations

- Live verification proves current source identity/status at one point in time;
  it is not a lease. The remote synthesis step must use the mapping immediately
  and recheck on source drift/error.
- This lane does not yet issue a NotebookLM question or verify a remote claim;
  NLM-002 and NLM-003 remain separate evidence gates.

## Next move

Advance to NLM-002: compare local-only and source-scoped NotebookLM synthesis
for usefulness, correctness, latency, and failure behavior.
