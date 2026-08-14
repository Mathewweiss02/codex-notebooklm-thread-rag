# ADR-005: Query-isolation topology

## Status

Accepted for the current release line; replica fan-out remains a gated
research capability.

## Decision

Use the local temporal CLI as the default authority. When NotebookLM
synthesis is explicitly requested, use the dedicated retrieval notebook with
source-scoped, sequential asks by default. Allow prompt packing only as an
explicit experimental mode, capped by the structural/quality gates and
verified per question. Keep the persistent human CLI-chat notebook completely
outside automated retrieval and benchmark reset paths.

Do not implement same-notebook parallel asks. Do not use repeated `--new` calls
as a pool primitive. A true parallel mode may use isolated retrieval-notebook
replicas only after explicit approval, source synchronization, account-safety
checks, bounded concurrency, cancellation, and the local verifier are all in
place.

## Evidence

- PQ-001 proved deterministic pack construction and fail-closed structural
  parsing for 16 development cases and pack sizes 1/2/4/8, but did not prove
  live answer quality or concurrency.
- PQ-002 confirmed that CLI `--new` deletes the notebook's current server-side
  conversation and that `--conversation-id` resumes only an already-known
  conversation. The public CLI has no safe conversation-pool provisioning
  command.
- PQ-003 showed current quota arithmetic can hold isolated replicas, but pool
  size 8 would require 1,176 aggregate source copies at the conservative
  current corpus size; quota arithmetic does not prove rate or quality safety.
- NLM-002/NLM-003 showed remote transport/source scope success is not factual
  acceptance: the final four-case rerun promoted 0/4 answers, so local fallback
  must remain authoritative.
- The historical four-question packed experiment reached 4/4 candidate recall
  and 3/4 raw Top-1 in one observation, but the sample was too small and is not
  a release gate.

## Consequences

### Positive

- User chat history is protected by topology, not operator memory.
- Exact temporal questions remain fast and deterministic locally.
- Packed/parallel research can evolve behind explicit gates without changing
  everyday CLI semantics.
- Replica cost and source freshness become observable design variables.

### Tradeoffs

- Sequential remote synthesis remains slow compared with local selection.
- Prompt packing needs live per-question quality evidence before promotion.
- Replica fan-out duplicates source synchronization and consumes account
  capacity; it is not a default free-tier optimization.

## Revisit conditions

Reopen this ADR only when a live, sealed development/holdout experiment shows
that a candidate faster topology preserves citation-supported quality,
conversation isolation, freshness, account health, and bounded failure
recovery. Any live replica creation requires explicit user approval.
