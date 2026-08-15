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

- Reproduce and close the live development retrieval-quality failure before
  spending another holdout or starting live replica concurrency. The original
  frozen run is below the release gates, while the newer source-scoped route
  still needs a healthy NotebookLM cooldown, three consecutive frozen passes,
  and a fresh sealed holdout. Rate-limited attempts are execution errors, not
  quality evidence.
- REL-002: complete the seven-day or reset fourteen-day soak and rollback
  evidence.
- PQ-006 remains separately gated on explicit isolated-replica approval.

## Latest evidence

- The latest retrieval state contains 145 projected threads.
- The exact committed benchmark-hardening gate at `46c197d` passed 48 Node tests
  and 219 Python tests, plus
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
- PQ-003 modeled replica capacity for pools 1/2/4/8/16/32/50; all fit the
  configured capacity model, but no live replicas were created.
- REL-001 initially found a stale handoff representing 140 threads and 15,990
  events while the current projection state had 144 threads and about 16,050
  events.
- The wall-clock release monitor is active from the protected-evidence reset
  boundary at 2026-08-15T04:46:31Z after the sync mitigation: 6 clean eligible
  runs, 0 failures, and 1.0 observed hours of the required 168. The prior
  pre-mitigation failure remains retained before this boundary; the new
  seven-day gate is correctly open.
- The stable-snapshot temporal refresh is wired into the retrieval runner and
  is protected by a recoverable SQLite overlap lock. The latest installed
  refresh completed successfully with 16,671 temporal events, 145 path-free
  thread metadata records, zero quarantines, nine
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
- The full repository gate now passes 48 Node tests and 224 Python tests, plus
  compilation, PowerShell parsing, and all operational integrations.
- The certification ledger contains 133 rows: 117 retained passes, 8 covered
  rows, and 8 pending release evidence. Versioned local-certification packets
  retain 101 focused deterministic cases, including local fallback across
  remote failure classes, bounded Windows file-lock retry, process-kill
  recovery, schema migration, overlapping-refresh serialization, paired
  rollback, derived-index removal/rebuild, query-error redaction,
  ambiguous-time disclosure, cross-runtime redaction parity, and explicit
  local performance gates. The eight covered rows now have explicit aggregate
  evidence for packed sizes 1/2/4/8 and the adaptive rate-limit mock, while
  the post-install resource soak and committed-revision/CI release proof remain
  open. The pending rows are the live explicit-conversation and isolated-
  concurrency experiments.
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
- The current-corpus performance packet passed cold rebuild, warm day, cold day,
  and complete week-context gates: P95 values were approximately 4.54 s,
  358 ms, 786 ms, and 2.32 s respectively; the week pack included 1,182/1,182
  events at its explicit large-period budget.
- The runner now retains aggregate resource diagnostics in each new report:
  working-set, private bytes, handle count, and processor-time samples. This
  is implementation readiness for the idle/resource soak, not a soak pass.
- The resource-aware retrieval soak monitor now reads the protected append-only
  evidence surface. The boundary was reset after operational retention removed
  older reports; its post-mitigation boundary currently has 6 eligible normal
  runs, 1.0 observed hours, zero failures, zero missing-step runs, and zero
  missing-resource reports. The 168-hour gate is open; the pre-mitigation
  failure is retained outside this new certification boundary.
- Across the latest 10 resource-bearing retrieval runs, the runner peaked at
  84.4 MiB working set, 70.3 MiB private bytes, and 626 handles; this shows no
  repo-runner memory-growth signal. The separate large Node process group on
  the desktop is `xcodebuildmcp`, not the NotebookLM sync runner.
- The separate persistent-chat scheduler has also produced its first
  post-install resource-bearing normal report with status `ok`. It remains a
  health/observability signal only and is intentionally excluded from the
  retrieval temporal soak because it does not run the temporal-refresh step.
- The frozen live development retrieval run on the disposable notebook
  completed all 40 cases. Its raw report was 28/32 positive Top-1, 31/32
  candidate recall, and 8/8 negative false positives. The candidate-only local
  verifier recovered 31/32 hybrid Top-1 and abstained on all 8 negatives, but
  the required 100% candidate-recall and 97.5% hybrid gates remain failed.
  A local-candidate union reached 32/32 combined coverage but degraded hybrid
  Top-1 to 30/32, so it is not promoted. The persistent chat notebook was not
  queried or reset.
- A bounded development-only retry experiment raised the semantic minimum to
  four candidates. It completed 40/40 cases but declined to 30/32 candidate
  recall and 30/32 hybrid Top-1, with a higher latency tail, so the default
  minimum remains two. This is retained as negative experiment evidence, not
  as a release result.
- A separate max-three-attempt experiment was intentionally bounded to a
  30-minute process budget. It completed 18/40 cases before the budget ended,
  so it has no quality score; the observed tail confirms that a third remote
  attempt is not suitable as the default UX. The partial run was not promoted
  or mixed into the frozen benchmark evidence.
- A negative-case audit rejected automatic local recovery after remote
  candidates failed local verification: it produced weak candidates for all
  eight negative cases. The final behavior therefore fails closed for an
  unverified remote result; explicit local fallback remains limited to remote
  failure or no-candidate paths.
- A source-scoped R&D probe used local candidates for one known development
  miss. Scoping NotebookLM to five candidates still placed the expected task at
  citation rank 7; scoping to two improved it to rank 2, but neither produced
  Top-1 and both took about 65–87 seconds. Source scoping remains a synthesis
  experiment, not a promoted retrieval fix.

## Fresh default live run and full-depth local recall

- A fresh default-policy run on the disposable retrieval notebook completed all
  40 development cases. It recorded 30/32 semantic candidate recall, 26/32
  raw citation-order Top-1, 30/32 hybrid Top-1, 0/8 hybrid false positives,
  and 2/32 false negatives. Latency was approximately 65.8 seconds at P50,
  127.4 seconds at P95, and 259.7 seconds maximum. The run failed the frozen
  development gates and remains development evidence only.
- A separate local-only benchmark searched the current 145-thread projection
  at candidate limit 145. It found all 32/32 positive cases with zero local
  search errors. The expected rank reached 78 for the hardest positive, which
  demonstrates full-corpus coverage but not acceptable local Top-1 ranking or
  live NotebookLM performance.
- Conditional local-union calibration reached 31/32 combined candidate
  coverage at small union sizes but never exceeded 30/32 hybrid Top-1, so no
  union or automatic local recovery policy was promoted.
- A full 40-case local-first/source-scoped hybrid experiment using the top 80
  deterministic local threads per query passed 32/32 positive candidate recall,
  32/32 hybrid Top-1, and 0/8 hybrid false positives. All 40 cases stayed
  inside their selected source scopes with zero execution errors. Latency was
  approximately 48.6 seconds at P50, 87.5 seconds at P95, and 249.1 seconds
  maximum. This is one passing development experiment, not a production
  default or release certificate; the long tail requires a bounded policy and
  the route still needs three frozen runs plus a fresh holdout.
- The first full adaptive-retry source-scoped run preserved 32/32 positive
  candidate recall and 32/32 hybrid Top-1 but exposed 1/8 false positives after
  an empty initial response was followed by one plausible retry citation. A
  broad quorum fix over-abstained on legitimate one-thread positives, so the
  committed policy now gates only sparse-initial-response retries. A later
  live run was invalidated by NotebookLM rate limiting across all semantic
  attempts; the benchmark now records that as an execution error and applies
  bounded rate-limit backoff. A post-cooldown smoke is still rate-limited, so
  no adaptive route pass has been counted. The benchmark now stops on a
  terminal rate-limit case and scores sealed aggregate reports from in-memory
  records before hiding per-case details.
- The committed repository gate at `46c197d` passes 48 Node tests, 219 Python
  tests, compile checks, and all 11 integration steps; the exact
  aggregate proof is retained in
  `.rnd/temporal-memory/full-gate-run-20260815-commit-46c197d.json`. This proves
  local correctness of the patch, not live NotebookLM availability or final
  release readiness.
- GitHub draft PR #3 remains at the older remote head and has only its
  historical Windows check; the current branch has not been pushed or merged
  because the live retrieval, soak, concurrency, and final CI gates remain
  open.

## RND-014 policy checkpoint

- A development-only replay compared 6,480 explicit ranking policies across
  the visible dev1/dev2/dev3 and sibling-v3 reports without opening the sealed
  holdout. The current baseline scored 31/32, 30/32, 32/32, and 12/12 hybrid
  Top-1 respectively, with zero visible false positives.
- The best zero-visible-false-positive candidate preserved dev3 and sibling
  passes and improved dev2 from 30/32 to 31/32. Its weights are captured as
  the named opt-in `generalization-v1` policy; baseline remains the default
  because the candidate cannot repair missing remote references and has no
  live or holdout evidence yet.
- The benchmark and CLI now record an explicit `rankingPolicy` field. No
  production default has been promoted from this replay.

## Current continuation checkpoint

- The current local candidate baseline recovered all 32/32 development positives
  at candidate depth 80 on the 145-thread projection with zero local-search
  errors. This is local candidate evidence, not remote semantic or hybrid proof.
- The latest one-case source-scoped smoke used transport retries set to zero,
  was rate-limited, and failed closed after one classified event;
  no live quality score was counted and persistent chat was not touched.
- The first post-policy `generalization-v1` one-case canary was also
  rate-limited and failed closed after one classified event in about 6.99
  seconds. It is execution evidence only; the policy remains unpromoted.
- The post-cooldown smoke is sealed as execution-error evidence only; the live
  retrieval gate remains unmeasured rather than falsely scored.
- The scheduler doctor now treats an explicitly active `Running`/`Queued` task
  as healthy while still failing disabled, stale, or failed-ready tasks; direct
  regression coverage and the full 48/221 repository gate pass on the fix.
- The patched skill was installed globally with a recoverable backup; the
  repository and installed doctor scripts have matching SHA-256 hashes, and
  the live retrieval doctor passes all 40 checks.

## Certification principle

Certified means zero known P0-P2 defects, zero failed or waived mandatory
gates, all modeled cases passing, verified recovery and rollback, bounded
resources, and successful shadow/canary/soak evidence. It does not claim that
unknown bugs are mathematically impossible.
