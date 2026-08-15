# PQ-004 Result

## Decision

Accepted ADR-005. The production topology is local-first plus optional
source-scoped sequential NotebookLM synthesis. Prompt packing is opt-in and
experimental. Same-notebook parallelism and repeated `--new` fan-out are
rejected. Isolated notebook replicas remain a gated future path requiring
explicit approval.

## Why

This is the smallest topology that preserves the user's persistent CLI chat,
keeps exact temporal retrieval deterministic, and respects the existing local
claim verifier. The evidence does not justify making remote synthesis or
parallel fan-out the default.

## Next gate

Advance to PQ-005: implement a bounded executor whose safe default is one
worker, whose packed mode is explicit, and whose concurrency values above one
are rejected unless an approved isolated-replica topology is supplied.
