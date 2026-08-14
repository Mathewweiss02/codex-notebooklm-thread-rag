# REL-001 Result — Pass After Freshness Integration Fix

## Initial shadow finding

The first read-only replay was intentionally run before changing production
state. It found a freshness defect: the existing temporal handoff represented
140 threads and 15,990 events, while the current projection state replay
represented 144 threads and approximately 16,050 events. Both SQLite files
were internally valid, so the defect was missing refresh integration rather
than corruption.

## Corrective implementation

- Added `scripts/thread_temporal_refresh.py`.
- The helper snapshots projection state, copies source files to a stable
  staging area, retries source-change races, validates the handoff and a
  temporary index, then promotes derived state with digest verification.
- Non-visible oversized lines remain disclosed as diagnostics; quarantines,
  malformed lines, and oversized visible lines fail closed.
- Wired the refresh into the retrieval-profile runner after projection and
  before remote NotebookLM sync.
- Added temporal integrity/freshness checks to the doctor.
- Installed the complete temporal runtime set at the scheduler’s configured
  skill path. The chat profile has `TemporalRefresh=false`.

## Canary evidence

- Runner dry run: 6 steps present and zero exit for temporal refresh and sync
  planning.
- Live retrieval runner: 6 steps completed successfully—auto-enroll,
  auth-refresh, projection, temporal-refresh, sync, and retention.
- Final temporal promotion: 144 state threads, 16,058 canonical events,
  16,058 source references, zero quarantines.
- Production SQLite verification: integrity passed and its event/manifest
  digests matched the promoted handoff.
- Live retrieval source map: 144 threads, 146 mapped parts, zero missing,
  mismatched, stale, or untracked sources.
- Retrieval-profile doctor: 40/40 checks passed on the final run.
- Persistent chat-profile doctor: 27/27 checks passed.

## Gate decision

`REL-001` passes after the freshness defect was fixed and re-tested. The next
release gate is `REL-002` soak testing. Full certification is not claimed yet:
the sealed holdout still needs externalization, destructive recovery drills
remain, and PQ-006 live replica concurrency remains explicitly gated.
