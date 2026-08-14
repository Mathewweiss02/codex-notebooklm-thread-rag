# PQ-006 Run Packet: Live concurrency ramp

## Objective

Measure quality-adjusted throughput at isolated retrieval-notebook pool sizes
1, 2, 4, and later 8/16 only if every prior level passes. Metrics must include
per-question verifier acceptance, source/citation scope, cross-talk, latency,
HTTP/auth/rate-limit errors, cancellation/orphan work, CPU/memory, and source
freshness.

## Current gate

This packet is prepared but not executed. Live replica creation and bulk source
copying require explicit user approval because they mutate the Google account,
consume NotebookLM source/notebook quota, and create cleanup obligations.

## Preconditions

- ADR-005 remains accepted.
- Replica source synchronization is isolated from the persistent chat notebook.
- Each worker has a distinct notebook ID and a verified current source map.
- The executor has a bounded worker count, cancellation, per-worker timeout,
  circuit breaker, explicit adaptive rate-limit backoff, and aggregate-only
  report. Rate-limit classification must be supplied by the transport adapter;
  ordinary failures cannot silently consume the rate-limit budget.
- A one-worker control run passes before any two-worker run.
- A failure at any level stops the ramp and preserves the last-known-good
  topology.

## Stop conditions

Stop on any cross-talk, persistent-chat mutation, citation misassignment,
verifier regression, unexpected retry burst, rate-limit/auth warning, orphaned
work, source drift, or unexplained latency/quality change.
