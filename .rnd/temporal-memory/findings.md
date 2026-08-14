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
