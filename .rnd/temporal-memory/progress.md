# Temporal Memory Execution Progress

## 2026-08-14 — master plan created

- Mapped canonical extraction, temporal indexing, context packing, NotebookLM routing, parallel execution, verification, CLI, operations, and release gates.
- Defined 14 implementation/validation phases, five ADR decisions, 28 ordered queue items, measurable performance floors, defect policy, rollout stages, and completion artifacts.
- Created the release-blocking certification matrix across time semantics, indexing, context, NotebookLM, concurrency, performance, security, UX, operations, and rollback.
- Preserved the evidence boundary: message-level timestamps exist; date-filtered semantic search is not exhaustive; the measured busy day had 10 threads, 291 visible messages, and about 420K visible characters; all 10 mapped to 11 ready sources in both notebook roles.
- Kept concurrency claims honest: prompt packing remains experimental; shared null-conversation asks are serialized/unsafe; 50-way fan-out is not authorized or promised.

## 2026-08-14 — TM-000 complete

- Ran the full current repository suite successfully: 22 Node tests, 60 Python tests, compilation, PowerShell parsing, runner/doctor/auth/ACL/install/config/scheduler integrations.
- Captured the app-server aggregate inventory: 140 visible tasks and a non-content corpus fingerprint; recorded that README's older 130-task statement is stale.
- Captured three local semantic-search timing runs without NotebookLM hydration.
- Added synthetic temporal oracle fixtures covering visible-role filtering, invalid/missing timestamps, active/archive deduplication, half-open day bounds, spring-forward, and fall-back days.
- Fixed and reran the oracle harness; three runs produced identical 4/4 results and digest `1374348f89aa011c236678e2c9796ac14f70836c96d19b392b564f305d3a2e84`.
- No product, scheduler, authentication, NotebookLM, or runtime state was changed.

## 2026-08-14 — TM-001 complete

- Approved the machine-readable `temporal-memory-v1` contract and its human-readable packet.
- Locked local authority, UTC storage, explicit timezone interpretation, half-open ranges, quarantine behavior, canonical identity, exhaustive-before-semantic selection, provenance, local fallback, and concurrency safety defaults.
- Recorded deferred empirical choices for the index engine/content boundary, segmentation threshold, context allocation, and NotebookLM isolation topology.

## 2026-08-14 — TM-002 complete

- Verified Python 3.12.4 / SQLite 3.45.3 in the pinned runtime and Node 24.11.1 experimental `node:sqlite` availability.
- Ran the synthetic 1K/5K/20K comparison across text-in-SQLite, metadata-plus-sidecar, and content-addressed modes.
- Selected the stable Node parser -> versioned redacted event handoff -> Python stdlib SQLite boundary.
- Selected sanitized text in SQLite for fast context assembly; rejected blob-per-content as the default because the 100-message read sample took seconds rather than milliseconds.
- Recorded ADR-001, ADR-002, the run packet, and result limitations. No product code was added in the comparison lane.

## 2026-08-14 — TM-003 complete

- Added the Node `temporal-event-v1` extractor at the existing projection parser boundary.
- Added atomic handoff writes, source-change detection, path-free provenance, explicit timestamp quarantine, visible-overflow blocking, and UTF-8 BOM tolerance.
- Added an independent Python oracle and synthetic raw JSONL fixture set.
- Extractor regression tests passed 4/4; independent parity passed three times with one signature digest.
- A real-corpus sample was not claimed: the aggregate inventory intentionally omits session paths, so a controlled path-bearing manifest is still a later evidence task.

## 2026-08-14 — TM-004 complete

- Added the crash-safe SQLite temporal index and derived-state verification path.
- Added active/archive canonicalization, stale-event removal, no-op detection, transaction rollback on bad input, corruption/schema fail-closed behavior, rebuild backups, and half-open timestamp queries.
- Full suite remained green at 26 Node tests and 63 Python tests; focused index tests passed 4/4.
- Real-corpus replay, process-kill/disk-full injection, and migration history remain release gates.

## 2026-08-14 — TM-005 complete

- Added the Node ICU-backed timezone and temporal-expression resolver.
- Verified calendar/rolling semantics, Monday/Sunday week starts, future/empty periods, half-open bounds, and DST-short/DST-long days.
- Rejected ambiguous repeated local times and nonexistent spring-gap times unless an explicit offset is supplied.
- Full suite remained green at 32 Node tests and 64 Python tests.
- Documented the Windows Python `tzdata` absence and kept the runtime dependency surface unchanged.

## 2026-08-14 — TM-006 complete

- Ran the independent 17-event segmentation experiment against 15/30/60/120-minute candidates.
- Selected `activity-segmentation-v1`: partition by thread, sort by UTC timestamp and event ID, start a new segment only when the gap is strictly greater than 60 minutes, and do not split at midnight.
- The 60-minute candidate was the only exact 8-activity partition with pairwise precision/recall/F1 of 1.0 and zero false merges/splits.
- Repeated the complete result three times; the result-file SHA-256 was `7207F4B85990C5792AD84EEB8B081126E3260BBF989DEB8AA8E558BFD9DCD0F0` each time and the canonical result digest was `b4f57673f7c577b70de5f11ad2f6cac658bb54ec2bc1cbd357efe9c8e6606398`.
- Recorded ADR-003, the versioned policy artifact, and the updated contract reference. The threshold remains a synthetic starting policy until real-corpus calibration and sealed holdout gates pass.

## 2026-08-14 — TM-007 complete

- Added the local-only `temporal-context-pack-v1` implementation, full-history segment reads, Node ICU local-day bridge, explicit mode budgets, round-robin segment coverage, omission accounting, provenance, empty results, stale-range rejection, and drill-down scope.
- Focused context tests passed 4/4 and local-day tests passed 2/2.
- Full repository verification passed: 34 Node tests, 67 Python tests, compilation, PowerShell parsing, and all runner/doctor/auth/ACL/install/config/scheduler integrations.
- The packer deliberately produces evidence only; it does not generate NotebookLM claims or alter any notebook conversation.

## 2026-08-14 — TM-008 complete

- Added `temporal-cli-v1` with `when`, `recap`, `context`, `find`, and `compare`; JSON is the default and `--human` is only a presentation layer.
- Actual subprocess tests covered every command, shared resolver fields, exact local evidence counts, period comparison, and nonzero machine-readable invalid-range errors.
- Full repository verification passed: 34 Node tests and 70 Python tests, compilation, parsing, and all existing operational integrations.
- README now exposes the local temporal CLI and labels the old 130-task/132-source deployment figures as historical; the current 140-task inventory is identified as live baseline evidence.
- During the first real-corpus NLM-002 invocation, a Windows cp1252 stdout failure was caught on a non-ASCII message. The CLI, context packer, source mapper, and synthesis runner now force UTF-8 stdout with backslash replacement; the regression is covered by a non-ASCII CLI fixture.

## 2026-08-14 — TM-009 complete

- Updated the installed skill and operations reference so broad temporal requests route to the local CLI before semantic NotebookLM search.
- Added a machine-readable route table with six cold-start cases and executable documentation tests; 3 routing tests passed.
- Full repository verification passed: 34 Node tests, 71 Python tests, compilation, parsing, and all existing operational integrations.
- The persistent CLI-chat notebook remains outside automated temporal routing.

## 2026-08-14 — NLM-001 complete

- Added the read-only `temporal-source-map-v1` mapper with retrieval-role, disposable-chat, policy, revision, local digest, lineage, title, and source-ID checks.
- Fixture tests passed for current mapping, missing thread degradation, projection drift, and chat-role rejection.
- Live read-only verification mapped all 140 current retrieval threads to 142 current parts; all 142 live source IDs matched with zero missing, title mismatch, or bad status. The persistent chat config was excluded.
## 2026-08-14 — NLM-002 complete

- Added the sequential source-scoped synthesis experiment and parser tests. On the fixed real-corpus `today` boundary, local selection returned 55 canonical events in about 0.2 seconds; four disposable-notebook CLI calls all succeeded, all citations stayed in scope, and mean remote latency was about 43.5 seconds per case.
- Recorded ADR-004: local temporal retrieval remains authoritative and NotebookLM is optional synthesis only after a complete local scope and current source mapping. Claim-level factual verification is the NLM-003 gate; parallelism remains unproven.

## 2026-08-14 — NLM-003 complete

- Added `temporal-claim-verifier-v1` with fail-closed local context, source scope, projection digest, citation marker, cited-text, timestamp, and conversation-state checks.
- Verifier fixtures passed 9/9. The standalone verifier emits only aggregate verdicts and answer hashes; raw answers and cited passages remain in memory.
- Final live rerun: 4/4 remote transports succeeded and 4/4 source scopes were valid, but 0/4 answers were promoted; all abstained on `CITATION_EVIDENCE_UNMATCHED`. Local fallback therefore remained authoritative.
- The negative result is intentional evidence: transport and source-ID success do not imply factual support. Prompt packing may improve the answer contract later, but it cannot weaken this gate.

## 2026-08-14 — VAL-001 complete

- Added the independent validation runner and 19-case development/10-case holdout temporal suite.
- Corrected six benchmark expectation mistakes discovered by the first run; the final rerun passed 19/19 development and 10/10 holdout cases with stable result digests.
- Covered calendar/rolling periods, half-open boundaries, DST, leap/month boundaries, timezone regrouping, deterministic ties, empty future periods, and invalid input classes.
- The holdout is currently local and digest-sealed rather than cryptographically hidden; final release certification must move it outside the repository.

## Current release lane

## 2026-08-14 - REL-001 complete

- The first shadow replay exposed a real freshness defect: the temporal
  handoff/index lagged the current projection state.
- Added the staged `thread_temporal_refresh.py` path with stable source copies,
  bounded retry for active-file races, fail-closed diagnostics, temporary
  index verification, and post-promotion digest parity.
- Wired temporal refresh into the retrieval runner and added doctor checks for
  temporal integrity and freshness. The persistent chat runner does not own
  the shared refresh.
- The retrieval dry run and live six-step canary passed. The latest live state
  contains 144 projected threads and 146 current NotebookLM source parts; the
  temporal index contains 16,058 events, 16,058 references, and zero
  quarantines.
- Final retrieval doctor evidence passed 40/40 checks; chat doctor evidence
  passed 27/27 checks. The source mapper found zero missing, stale, mismatched,
  or untracked sources.
- REL-001 is complete. The next lane is REL-002 soak and rollback evidence;
  PQ-006 remains blocked on explicit isolated-replica approval.

## Historical queue record (superseded)

Run `PQ-002`: inspect the NotebookLM CLI conversation lifecycle for
non-destructive explicit conversation pools. PQ-001's offline structural gate
passed 7/7 tests; 16 development cases produced 30 deterministic pack plans
across sizes 1/2/4/8, with stable repeated suite and prompt-plan digests.

PQ-002 completed: read-only CLI/source inspection confirmed that `--new`
deletes the notebook's current server-side conversation, `--conversation-id`
only resumes an already-known conversation, and the public CLI has no
non-destructive conversation-pool provisioning command. Same-notebook fan-out
is therefore rejected; PQ-003 now models isolated notebook replicas without
creating them.

PQ-003 completed: live quota arithmetic and the offline replica planner show
that pool sizes 1/2/4/8 are source-capacity-feasible with 93 steady source
slots per replica at the conservative 147-part input. Pool size 8 would copy
1,176 source parts, so quota feasibility is not a performance or safety claim.
No live replica was created. PQ-004 now chooses the topology.

PQ-004 completed: ADR-005 selects local-first plus optional sequential
source-scoped synthesis. Prompt packing stays experimental, same-notebook
fan-out is rejected, and isolated replicas require explicit approval. PQ-005
now implements the bounded executor and explicit failure semantics.

PQ-005 completed: the executor passed 8/8 focused tests and was wired into a
fresh real NLM-002 run. The run completed 4/4 transports and 4/4 source-scope
checks with complete 55/55 local coverage; mean remote latency was about 40.1
seconds per case and the verifier promoted 0/4. PQ-006 remains a gated live
concurrency experiment, not a default behavior.

PERF-001, RES-001, SEC-001, and OPS-001 completed. Local context performance
measured about 202 ms P50 standard and 203 ms P50 deep across supported period
cases; a 1,017-event week-to-date pack became complete at an explicit larger
budget in about 831 ms. Failure-injection, ACL/redaction, dependency audit,
live doctors, scheduler console-free checks, and the 108-test full gate passed.
The next safe gate is REL-001 shadow/canary validation; PQ-006 remains gated on
explicit replica approval.

## 2026-08-14 — certification plan refreshed

- Reconciled the durable plan with the latest evidence: 42 Node tests and 135
  Python tests were green at the last full run; the local certification packet
  has 23 exact deterministic cases; the matrix is 31 pass, 78 covered, 24
  pending, and zero fail/blocked rows.
- Recorded current live boundaries: 16,141 temporal events, 16,141 source
  references, zero quarantines, 145 requested source-mapped threads across 147
  ready parts, and seven post-boundary soak runs covering about 1.434 hours.
- Reaffirmed that local evidence is authoritative. The last remote canary had
  successful transport and scope checks but zero promoted answers because the
  verifier found unmatched citation evidence.
- Added the finish sequence for context-signal extraction, project filtering,
  migration and failure-injection coverage, benchmark sealing, efficiency
  profiling, isolated parallel-query experiments, soak, rollback, and final
  release certification. No live replicas or parallel load were launched in
  this planning-only pass.
- A focused local-fallback test was previously attempted but its output was
  truncated before the result could be established. The next action is a
  bounded rerun; no certification row will be marked from that attempt.
- Planning-audit tooling notes: one recursive file discovery timed out after
  returning the existing planning files, and one progress read used the wrong
  working directory before being corrected. Neither affected product state.

## 2026-08-14 — local correctness closure

- Added deterministic local fallback for simulated remote outage, expired auth,
  HTTP 429/503, and timeout failures. Four fallback cases pass and retain only
  aggregate diagnostics plus locally verified candidate evidence.
- Added conservative context signals for intent, completion, unresolved work,
  artifacts, and decisions. Signals carry event-level provenance and are
  validated against the selected temporal evidence before publication.
- Added exact path-free project filtering by workspace label/hash across the
  temporal CLI and context packer. Missing metadata fails closed.
- Added schema-v1-to-v2 in-place migration with a migration ledger and tests
  for unsupported/corrupt state and explicit rebuild recovery.
- Added refresh-level overlap serialization and a matched handoff/index rollback
  rehearsal that leaves canonical state unchanged.
- Reran the local certification packet: 35/35 cases pass. The 133-row ledger
  is now 43 pass, 78 covered, 12 pending, zero fail/blocked.

## 2026-08-14 — installed runtime reconciliation

- Installed the current skill and verified exact source/installed script parity
  at 56/56 files.
- A scheduled older-runtime run was observed reverting the derived temporal
  index to schema v1 after a source refresh. The current install plus a real
  refresh recovered schema v2, 145 path-free metadata records, 16,175 events
  at the latest no-op verification, zero quarantines, and matching
  handoff/index digests.
- Installed retrieval doctor passed 40/40 checks; persistent-chat doctor passed
  27/27 checks.
- The complete repository gate now passes 43 Node and 152 Python tests, with
  all compile, parser, runner, doctor, auth/ACL, installation, configuration,
  and scheduler integration steps green.

## 2026-08-14 — soak evidence refresh

- Refreshed the read-only wall-clock monitor from the original release
  boundary. It now retains 10 eligible production runs, zero failed or
  malformed runs, a maximum observed gap of 0.257 hours, and 2.249 hours of
  continuous evidence. The 168-hour gate remains open.

## 2026-08-14 — rate-limit control

- Added a thread-safe adaptive rate-limit controller to the bounded executor.
  It requires an explicit classifier, honors bounded `Retry-After`, applies
  capped exponential backoff, and stops after a finite rate-limit event
  budget. Fake-clock burst, retry, invalid-classifier, and budget-exhaustion
  tests pass.
- Retained the deterministic rate-limit mock as covered evidence for PAR-019;
  the upstream live canary is intentionally not promoted from mock behavior.
- Reinstalled the skill and reran the complete repository gate: 43 Node and
  152 Python tests passed, alongside compile, parser, runner, doctor, auth/ACL,
  installation, configuration, and scheduler integrations.

## 2026-08-14 — committed full-gate evidence

- Extended `tests/run_all.ps1` with an optional aggregate-only `-ReportPath`
  output. The report records the tested commit, runtime labels, step timings,
  and pass status without repository paths, prompts, answers, credentials, or
  NotebookLM identifiers.
- Ran the complete gate at commit `ff2758e46f38a2ec9e35e3f28d40c8f2167ad744`;
  43 Node tests, 152 Python tests, compilation, parsing, runner, doctor,
  auth/ACL, installation, configuration, and scheduler integrations all
  passed. Retained report: `full-gate-run.json`.
- OPS-006 remains pending because the open draft PR's latest GitHub check is
  for an older commit; current-commit CI proof still requires an intentional
  push or equivalent external CI run.

## 2026-08-14 — resource-observable runner

- Added aggregate working-set, private-memory, handle-count, and processor-time
  samples to each new runner report. Child output, process paths, notebook IDs,
  prompts, and answers remain excluded.
- The runner integration now verifies the resource summary, and the full gate
  passed again at commit `eb62c608dbd2b4a58911c8a6bc1f7b4d560b947d` with 43
  Node tests, 152 Python tests, and all integration steps green.
- Reinstalled the skill so the live local runtime contains the new runner.
  The release soak boundary must be re-established from this installed
  revision; PERF-011 and OPS-005 remain pending until the new reports show a
  clean wall-clock window.

## 2026-08-14 — resource-aware soak monitor

- Added `--require-resource` to the release monitor. It validates aggregate
  sample count, working-set peak, private-memory peak, handle peak, and CPU
  delta, and fails closed when any eligible report is missing those fields.
- Added passing and failing unit coverage for the resource requirement. The
  previous timing-only monitor remains available for historical diagnostics;
  it is not sufficient for the final resource-aware soak.

- Reran the full gate at commit `877df8273f32c40cf32e49e9aacf3acadaffbe76`:
  43 Node tests, 154 Python tests, compilation, parsing, runner, doctor,
  auth/ACL, installation, configuration, and scheduler integrations passed.

## 2026-08-14 — resource-aware soak boundary

- The retrieval scheduler produced the first post-install normal report with
  eight resource samples and status `ok`.
- Started the retained resource-aware monitor from that run. It is honestly
  `open` at 2 eligible runs and 0.265 observed hours; both PERF-011 and OPS-005
  remain pending until the complete 168-hour window is clean.
- The persistent-chat task separately completed its first post-install normal
  run with resource telemetry. It is not counted toward the retrieval soak,
  preserving the temporal-refresh boundary and persistent-chat separation.

## 2026-08-14 — CI evidence binding

- Updated Windows CI to retain an aggregate full-gate report and fail if its
  commit SHA does not equal the checked-out GitHub revision. This closes the
  prior “green but stale evidence” ambiguity without adding private artifacts.
- Reran the local full gate at commit `3147358077b55c3fbbba7a5093212839635f1e18`:
  43 Node tests, 154 Python tests, compilation, parsing, runner, doctor,
  auth/ACL, installation, configuration, and scheduler integrations passed.
