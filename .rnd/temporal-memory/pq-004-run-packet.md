# PQ-004 Run Packet: Query-isolation topology decision

## Objective

Choose the default and experimental NotebookLM query topologies using the
completed structural, isolation, replica-capacity, local-authority, and claim-
verification evidence.

## Options

1. Sequential source-scoped asks, one remote request per question.
2. One packed source-scoped ask, with per-question sections and local
   verification for every answer section.
3. Isolated retrieval-notebook replicas, each with independent source state and
   a bounded worker pool.
4. Shared-notebook concurrent asks or repeated `--new` calls.

## Required decision criteria

- Persistent CLI chat cannot be deleted, contaminated, or silently continued.
- Local temporal selection remains complete and authoritative.
- Every promoted remote claim passes the local verifier.
- A faster mode must expose partial failure, cancellation, retry, and
  cross-talk rather than silently returning a partial aggregate.
- Default behavior must remain understandable and low-maintenance.

## Prohibited shortcut

Do not treat the upstream global RPC ceiling as a safe query-concurrency
setting. It bounds transport work; it does not create independent NotebookLM
conversation state.
