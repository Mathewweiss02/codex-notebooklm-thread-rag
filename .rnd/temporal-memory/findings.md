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
- The live soak is not complete: seven eligible runs and roughly 1.434 hours are evidence of a healthy beginning, not a seven-day certification result.

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
