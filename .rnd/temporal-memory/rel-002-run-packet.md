# REL-002 Run Packet — Soak and Rollback Evidence

## Objective

Exercise repeated temporal refreshes and the live scheduled path long enough to
detect drift, resource growth, stale success, source races, failed promotion,
and recovery defects.

## Accelerated gate

Run 14 deterministic cycles over a temporary fixture with:

- valid refresh and no-op behavior;
- event changes across cycles;
- intentional SQLite corruption and automatic derived-state rebuild;
- quarantined input that must fail closed without changing the last-good index;
- staging-directory cleanup and final integrity checks.

## Wall-clock gate

Observe the existing hidden scheduled task for seven days, or use a reset
fourteen-day observation window after any release-blocking defect. Retain only
aggregate status, timing, resource, freshness, and digest evidence. Do not
reset the persistent chat notebook or create replica notebooks during soak.

After the updated runner is installed, evaluate the new observation boundary
with `thread_temporal_release_monitor.py --require-resource`; this is separate
from the earlier timing-only monitor and must not inherit its start boundary.

## Pass criteria

- Every required cycle succeeds or fails with an expected stable code.
- No canonical loss, silent omission, stale-success health result, orphaned
  process, unbounded report growth, or unexplained resource trend. Each
  post-change runner report must include aggregate working-set, private-byte,
  handle-count, and processor-time diagnostics without raw child output.
- Recovery restores a verified derived index without deleting canonical source
  data.
- The wall-clock observation has no P0-P2 defect and no waived mandatory gate.
