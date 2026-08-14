# PQ-003 Result

## Capacity model

- Offline planner tests: 3/3 passed.
- Per-replica steady capacity: 240 source parts.
- Conservative source parts per replica: 147.
- Per-replica steady headroom: 93 source parts.
- Retrieval pool sizes modeled: 1, 2, 4, and 8.
- New replica counts: 0, 1, 3, and 7.
- Total notebooks after expansion: 2, 3, 5, and 9.
- Aggregate source copies: 147, 294, 588, and 1,176.
- Initial copy units for new replicas: 0, 147, 441, and 1,029.
- Worst-case full-refresh units per cycle: 147, 294, 588, and 1,176.
- All modeled rows preserve the source reserve and remain below the live
  notebook limit; this is capacity evidence only.

## Decision

An isolated-notebook pool is feasible on current quota arithmetic, but the
copy/refresh work grows linearly with pool size and the model says nothing
about rate limits, freshness lag, semantic quality, or account safety. Do not
create replicas solely because the quota permits them.

The safe architecture candidates are now explicit:

1. Sequential source-scoped asks: simplest, current default.
2. One packed ask: fewer remote calls, but it must pass per-question local
   verification and quality gates.
3. Isolated notebook pool: real parallelism, but it adds source duplication,
   synchronization, cleanup, and quota/rate-limit surface.

## Next gate

Advance to PQ-004: choose the topology using the PQ-001 structural result,
PQ-002 isolation rejection, the PQ-003 cost model, and the existing NLM-003
claim verifier. No live replica creation is authorized until that decision is
recorded and explicitly approved.
