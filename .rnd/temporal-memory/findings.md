# Temporal Memory Planning Findings

## Confirmed evidence

- Canonical Codex events already carry ISO timestamps at message level.
- Existing projections retain the message timestamp and source line, plus thread created/updated metadata.
- Existing `thread_search.mjs --today/--after/--before` applies time bounds only after query-matching messages are found. It is temporal semantic search, not an exhaustive period inventory.
- Thread creation date cannot determine activity date. Old threads can be resumed and contain new messages in the requested period.
- A measured busy local day (2026-08-12, America/New_York) contained 10 canonical active threads, 291 visible user/assistant messages, and approximately 419,758 visible characters.
- Those 10 threads were present in both live NotebookLM role configurations as 11 ready source parts, proving exact thread-to-source scoping is feasible for that sample.
- Raw day content can exceed a practical context budget, so complete selection and hierarchical compression are both required.
- The current NotebookLM CLI supports repeated `--source` arguments, enabling source-scoped asks after local thread selection.
- The pinned client serializes asks with no explicit conversation ID by notebook, and `--new` deletes the current server-side conversation. Naive same-notebook parallel asks are unsafe or serialized.
- Prompt packing has shown a large wall-time signal but only 3/4 accepted Top-1 on a four-question sample; it is experimental, not production-approved.
- Local verification is much faster than remote generation and should remain the authority and final gate.

## Main bottlenecks

| Class | Bottleneck | Why it is upstream |
| --- | --- | --- |
| Validation | No exhaustive date-first oracle/benchmark exists | Cannot prove “all activity” completeness |
| Architecture | Current search begins with semantic query matches | Generic “what did I do?” can omit unrelated but valid activity |
| Context | Busy periods are too large to inject raw | Requires deterministic hierarchy and budget accounting |
| Concurrency | Safe independent conversation topology is unproven | Throughput changes could corrupt chat state or citations |
| Tooling | Multiple scripts expose overlapping low-level interfaces | Fresh-task usability and maintenance suffer |
| Upstream | NotebookLM interface is unofficial and mutable | Requires canary, pin, rollback, and local fallback |
| Scale | Index/storage and source fan-out behavior at 10× is unproven | Current-corpus success does not prove growth behavior |

## Decisions already supported

- Build a local temporal authority before adding any NotebookLM timeline corpus.
- Treat day/week/month as computed views over message timestamps.
- Keep full transcript duplication out of NotebookLM unless a measured experiment proves it necessary.
- Resolve time phrases to explicit machine-readable boundaries and show them to the user.
- Use source-scoped NotebookLM only after local selection and follow with local verification.
- Keep persistent chat, disposable lookup, benchmarks, and concurrency experiments separate.
- Ramp parallelism gradually; do not treat “50” as a requirement or safe default.
- Make the final interface CLI-first and skill-invocable from a fresh Codex task.

## Open architecture questions

1. Which index boundary best reuses the Node parser while keeping SQLite stable and dependency-light on Windows?
2. Should sanitized message text live in SQLite, in content-addressed blobs, or only in canonical files?
3. What inactivity gap best defines activity segments without fragmenting coherent work?
4. How should context packs allocate budget among many small threads and one giant thread?
5. Can explicit conversation IDs be safely provisioned without destructive chat reset?
6. At what source/thread count does one source-scoped ask lose quality or exceed practical request limits?
7. Is prompt packing, isolated conversation IDs, notebook replicas, or a hybrid the best safe throughput topology?
8. What concurrency level produces the best quality-adjusted throughput before throttling or citation degradation?

## Tooling note

Sol Advisor orchestration could not run during the preceding architecture pass because its Windows plugin data directory was reported by Bun as POSIX mode `0666`, while the plugin requires `0700` and fails closed. No advisor verdict was fabricated or substituted. Plugin repair is separate from this product plan.

## Current certification findings — 2026-08-14

- The local temporal architecture is now strong enough for a controlled certification campaign: canonical message-level timestamps, a crash-safe SQLite index, DST-safe range resolution, hierarchical context packing, source-map verification, local claim verification, and a local-first CLI/skill route are all exercised by deterministic tests.
- The most important remaining correctness distinction is between transport success and accepted truth. NotebookLM can answer successfully while still failing local citation/evidence verification; such answers must remain abstentions rather than benchmark wins.
- The system should support broad-period questions by exact local enumeration first, then context packing, then optional NotebookLM synthesis. Daily/weekly duplicated NotebookLM corpora are not the default architecture because they add freshness and reconciliation cost.
- Same-notebook parallel asks are not a safe concurrency primitive. The plan must test packed prompts and explicit conversation IDs first, then use disposable isolated notebook replicas only after explicit approval and one-at-a-time validation.
- Parallelism is valuable only as quality-adjusted throughput. The scorecard must include correctness, citation alignment, isolation, retries, rate-limit behavior, cancellation, memory, CPU, and wall time; a faster but cross-talk-prone route is a failed experiment.
- The local fallback is now retained evidence: simulated remote outage, expired
  auth, HTTP 429/503, and timeout failures each return a locally verified
  candidate. The fallback is reported as degraded/local evidence and is never
  counted as raw remote retrieval quality.
- The live soak is not complete: 10 eligible runs and roughly 2.249 hours are evidence of a healthy beginning, not a seven-day certification result.

## New implementation findings — 2026-08-14

- Context signals are useful only as navigation metadata. Intent, completion,
  unresolved, artifact, and decision labels are conservative heuristics with
  event IDs, role, timestamp, digest, and source references; they are not
  accepted as independent factual summaries.
- Project filtering is safe when it uses path-free workspace labels or hashes
  carried in the manifest. Missing or stale metadata fails closed rather than
  silently broadening the query.
- Temporal index schema v1 can migrate in place to v2 with a recorded migration
  row. Unsupported versions, contract drift, and redaction-policy drift still
  require an explicit rebuild and preserve the last-good derived state.
- Refresh-level overlap requires its own lock in addition to SQLite writer
  locking. Without it, two valid refreshes could promote a handoff and index
  from different generations even though each artifact was individually valid.
- Rollback must treat the handoff and SQLite index as one verified generation.
  The rehearsal restores a matched previous pair and leaves canonical session
  state untouched.
- A real deployment-order defect was observed: a scheduled task using an older
  globally installed skill ran after a source refresh and restored a schema-v1
  derived index. Installing the current skill and rerunning the refresh fixed
  it. Source/installed parity and committed-revision proof are therefore
  release gates, not documentation niceties.
- The executor now has an explicit adaptive rate-limit controller: classified
  rate-limit errors consume a bounded event budget, honor bounded
  `Retry-After`, apply exponential backoff, and fail closed when the budget is
  exhausted. Deterministic fake-clock burst tests pass; this is covered mock
  evidence only until a live canary observes the real upstream behavior.
- Full-gate evidence should be retained at the tested revision, not inferred
  from console output. The optional aggregate report records the commit and
  step timings without path or content leakage; a stale CI result cannot be
  promoted to current-revision proof.
- Scheduler soak reports previously retained status and step timing only. The
  runner now records aggregate working-set, private-memory, handle-count, and
  processor-time samples around each child step. This improves leak/orphan
  detection without retaining child output or sensitive process metadata; the
  wall-clock gate must be re-established from the installed revision.
- The release monitor now has an explicit `--require-resource` mode that
  fails closed when any eligible run lacks valid aggregate resource fields.
  Timing-only history cannot accidentally satisfy the resource-aware soak.

## Live development retrieval finding — 2026-08-14

- The frozen 40-case disposable-notebook run completed with raw semantic
  candidate recall 31/32, raw citation-order Top-1 28/32, and 8/8 negative
  false positives. This is a failed development gate, not a holdout result.
- Candidate-only local reranking recovered 31/32 hybrid Top-1 and abstained on
  all eight negative cases. A separate union with the full local-candidate
  report reached 32/32 combined candidate coverage but degraded hybrid Top-1
  to 30/32, so union retrieval is not a default fix.
- The run used the disposable retrieval notebook and reset its conversation
  before each attempt; the persistent chat notebook was not touched. The next
  experiment must use development evidence only, preserve raw/combined/hybrid
  score separation, and finish before any sealed holdout or live replica ramp.

## Live minimum-candidate experiment — 2026-08-14

- A bounded development-only run with `minSemanticCandidates=4` completed all
  40 cases but declined to 30/32 positive candidate recall and 30/32 hybrid
  Top-1, versus 31/32 for the default two-candidate policy. Its latency tail
  was also higher, so the setting is retained as an explicit diagnostic
  control and is not promoted as the production default.
- The experiment used the same disposable retrieval notebook and preserved
  raw remote, combined, hybrid, false-positive, and latency measurements. It
  did not consume the sealed holdout or create replicas.

## Live max-three-attempt experiment — 2026-08-14

- A separate run with the default two-candidate stop and three permitted
  semantic attempts was bounded at 30 minutes. It completed 18 of 40 cases
  before the command budget ended and therefore has no valid quality score.
- The partial run was cleaned up after the timeout: only its verified parent
  and child benchmark processes were terminated, with no other Python or Node
  process targeted. The result remains private, incomplete evidence and does
  not alter the default two-attempt policy.

## Local recovery safety audit — 2026-08-14

- The proposed automatic local fallback after a remote candidate set failed
  local verification was rejected. On the frozen development negatives it
  produced at least one local candidate for all eight no-match queries, with
  top local scores ranging from 30.66 to 67.36; those scores are not a safe
  no-match discriminator.
- The implementation therefore fails closed when remote candidates exist but
  local authority cannot accept them. Deterministic local fallback remains
  available for remote outage, auth, timeout, or empty-semantic paths only.

## Source-scoped retrieval probe — 2026-08-14

- For one known development miss, the local fallback candidate set was used to
  select NotebookLM sources without changing the query or benchmark labels.
  Five selected sources yielded the expected thread at citation rank 7; two
  selected sources improved it to rank 2. Neither was Top-1, and observed
  latency was approximately 64.9 and 86.6 seconds.
- The result supports source scoping as a bounded synthesis tool, not as proof
  that local-first source selection fixes global retrieval. No production
  routing or release gate was changed.

## Fresh default live run and full-depth local recall — 2026-08-14

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
- The next quality experiment must test a separately labeled local-first /
  source-scoped route with full-depth local candidates, explicit negative-case
  abstention, and a bounded latency budget. It must not be counted as raw
  NotebookLM recall and must not modify the default route until it passes the
  same frozen gates.

## Local-first/source-scoped hybrid canary — 2026-08-14

- A sequential 40-case development canary selected the top 80 deterministic
  local candidates, mapped all current source parts for those candidates, and
  asked the disposable retrieval notebook with `source_ids` restricted to that
  set. The returned citations were then locally reranked and required to pass
  the existing local verification/abstention contract.
- The canary achieved 32/32 positive candidate recall, 32/32 hybrid Top-1,
  0/8 hybrid false positives, zero source-scope violations, and zero execution
  errors. This is a material improvement over the latest global default run
  (30/32 semantic recall and 30/32 hybrid Top-1).
- Latency was approximately 48.6 seconds at P50, 87.5 seconds at P95, and
  249.1 seconds maximum. The maximum was a negative case that abstained after
  a long remote response, so the route needs a hard per-query deadline and a
  truthful degraded result before it can be considered operationally ready.
- The canary is retained as one development pass only. It does not count as
  raw global NotebookLM recall, does not spend the sealed holdout, and does not
  justify changing the default until the route is implemented reproducibly,
  passes three frozen development runs, and passes a fresh holdout.

## Source-scoped retry and rate-limit findings - 2026-08-14

- The first complete adaptive-retry harness run achieved 32/32 positive raw
  candidate hits and 32/32 hybrid Top-1, but produced 1/8 hybrid false
  positives. The false positive came from an empty first response followed by
  a single plausible citation on the retry; accepting a one-candidate local
  consensus after that sequence was unsafe.
- A broad minimum-candidate quorum fix removed the false-positive pattern but
  also abstained on legitimate one-thread positive cases. That policy was not
  promoted. The retained rule is narrower: a sparse initial response followed
  by an under-quorum retry fails closed, while ordinary one-candidate results
  with non-empty initial evidence remain eligible for local verification.
- A subsequent full run was invalidated by upstream NotebookLM rate limiting:
  all 80 semantic attempts returned the pinned ChatError rate-limit response.
  Authentication and source enumeration remained healthy. The benchmark now
  records all-attempts-failed as an execution error, classifies rate-limit
  retries without exposing the message, and applies bounded backoff.
- No source-scoped route is certified or promoted from these runs. A fresh
  cooldown smoke must pass before another 40-case run is counted; then three
  consecutive frozen development passes and a fresh sealed holdout remain
  required.

## Benchmark safety and sealed aggregation - 2026-08-14

- The source-scoped benchmark now treats a failed case containing a classified
  rate-limit attempt as a circuit-breaker event: it stops the remaining cases,
  records `aborted` and `abortReason`, and never spends the rest of a run on
  requests that are already known to be throttled.
- Benchmark gates now score the in-memory records before the aggregate-only
  report surface is sealed. This preserves latency, error, scope, and
  rate-limit counts without writing per-case holdout details, and an aborted
  partial run cannot pass because hidden case records were omitted.
- The new behavior is covered by deterministic unit tests. No live quality
  score changed, and the rate-limited cooldown smoke remains invalid evidence.
