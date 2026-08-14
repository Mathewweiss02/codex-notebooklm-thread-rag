# Current Brief: Temporal Memory and Parallel NotebookLM

## Mission

Deliver a deterministic date/time memory layer and safe quality-preserving
NotebookLM throughput path that a fresh Codex task can use through one clean
CLI/skill contract.

## Current state

- Planning and system mapping are complete; implementation is in release
  validation.
- TM-000 through VAL-001, PQ-001 through PQ-005, and PERF/RES/SEC/OPS gates
  are complete.
- REL-001 passed after fixing a real temporal-index freshness integration
  defect.
- The local temporal CLI/index is authoritative for exact time questions.
- NotebookLM remains optional source-scoped synthesis; the persistent chat
  notebook is excluded from automated retrieval and reset operations.
- Same-notebook parallel fan-out is rejected. Isolated replica ramps remain
  explicitly gated on approval.
- `notebooklm_isolated_ramp.py` now supplies the dry-run and approval-gated
  live boundary for replica creation; no replica has been created.

## Governing recommendation

Build and operate the local temporal authority first. Add source-scoped
NotebookLM synthesis only after complete local coverage and current source
mapping. Treat packing and parallelism as separate experimental branches.

## Next item

- REL-002: complete the seven-day or reset fourteen-day soak and rollback
  evidence.
- PQ-006 remains separately gated on explicit isolated-replica approval.

## Latest evidence

- The latest retrieval state contains 145 projected threads.
- The full repository gate passed 47 Node tests and 162 Python tests, plus
  compilation, PowerShell parsing, and operational integrations.
- Temporal validation passed 19/19 development and 10/10 holdout cases; the
  holdout is still local and must be externalized before final release.
- Live source mapping passed 145/145 threads and 147/147 current source parts,
  with zero missing, mismatched, stale, or untracked sources.
- Source-scoped synthesis transported 4/4 sequential calls and kept 4/4
  citation scopes valid; the verifier promoted 0/4 claims, so local fallback
  remains authoritative.
- PQ-001 produced 30 deterministic pack plans across sizes 1/2/4/8. This is
  structural readiness only, not a live quality or concurrency claim.
- PQ-002 rejected same-notebook `--new` fan-out because it deletes the current
  server-side conversation. The pinned CLI is v0.8.0; an older v0.6.0 binary
  remains earlier on PATH and is not used by configured profiles.
- PQ-003 modeled replica capacity; no live replicas were created.
- REL-001 initially found a stale handoff representing 140 threads and 15,990
  events while the current projection state had 144 threads and about 16,050
  events.
- The wall-clock release monitor is active from the post-REL-001 boundary: 10
  eligible runs, 0 failed or malformed runs, and 2.249 observed hours. The
  seven-day gate is correctly still open.
- The stable-snapshot temporal refresh is wired into the retrieval runner and
  is protected by a recoverable SQLite overlap lock. The latest installed
  refresh completed successfully with 16,279 temporal events and source
  references, 145 path-free thread metadata records, zero quarantines, nine
  allowed non-visible overflow lines, and matching index/handoff digests.
- Schema version 1 was migrated in place to schema version 2 and the migration
  ledger is verified. A paired derived-state rollback rehearsal restores a
  verified previous handoff/index generation without touching canonical state.
- Remote outage, expired-auth, HTTP 429/503, and timeout cases now exercise a
  deterministic local fallback. Context packs expose conservative heuristic
  intent/completion/unresolved/artifact/decision signals with provenance, and
  exact path-free project filtering fails closed when metadata is unavailable.
- Direct index writers now serialize through a recoverable SQLite sidecar lock;
  concurrent-writer regression coverage passes.
- The full repository gate now passes 47 Node tests and 162 Python tests, plus
  compilation, PowerShell parsing, and all operational integrations.
- The certification ledger contains 133 rows: 70 retained passes, 55 covered
  rows, and 8 pending release evidence. The local-certification packet now
  retains 63 focused cases: 62 promoted exact deterministic edge cases,
  including local fallback across remote failure classes, bounded Windows
  file-lock retry, process-kill recovery, schema migration,
  overlapping-refresh serialization, paired rollback, derived-index
  removal/rebuild, query-error redaction, ambiguous-time disclosure, and
  redaction-policy mismatch/rebuild behavior, plus one covered adaptive
  rate-limit mock. The live rate-limit canary remains open.
  The 145-thread
  incremental benchmark also passes
  no-change P95 92.998 ms and one-thread-append P95 479.113 ms against the
  1-second/2-second floors; covered is intentionally not a pass.
- The safe live packed experiment passed hybrid expectation on 4/4 questions at
  pack sizes 1, 2, and 4, but only 7/8 at pack size 8; packing remains opt-in
  and no pack size is promoted as a certified quality default.
- The installed retrieval doctor passed 40/40 checks, including temporal
  integrity and freshness. The persistent chat doctor passed 27/27 checks.
- Source/installed script parity is exact at 63/63 files after installation;
  no raw path metadata is present in the temporal handoff.
- The runner now retains aggregate resource diagnostics in each new report:
  working-set, private bytes, handle count, and processor-time samples. This
  is implementation readiness for the idle/resource soak, not a soak pass.
- The resource-aware retrieval soak monitor restarted at the current installed
  skill boundary with 1 eligible post-install run, 0.0 observed hours, zero
  failures, and zero missing-resource reports. The 168-hour gate is open.
- The separate persistent-chat scheduler has also produced its first
  post-install resource-bearing normal report with status `ok`. It remains a
  health/observability signal only and is intentionally excluded from the
  retrieval temporal soak because it does not run the temporal-refresh step.

## Certification principle

Certified means zero known P0-P2 defects, zero failed or waived mandatory
gates, all modeled cases passing, verified recovery and rollback, bounded
resources, and successful shadow/canary/soak evidence. It does not claim that
unknown bugs are mathematically impossible.
