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

## Pass criteria

- Every required cycle succeeds or fails with an expected stable code.
- No canonical loss, silent omission, stale-success health result, orphaned
  process, unbounded report growth, or unexplained resource trend.
- Recovery restores a verified derived index without deleting canonical source
  data.
- The wall-clock observation has no P0-P2 defect and no waived mandatory gate.
