# ADR-004: Local Temporal Authority and Optional NotebookLM Synthesis

## Status

Accepted after NLM-002 development experiment; factual claim verification is
deferred to NLM-003.

## Decision

Use the local temporal index and CLI as the authoritative path for exhaustive
date/time selection, counts, event boundaries, and exact “when” questions.
Invoke NotebookLM only as an optional source-scoped synthesis layer after the
local selector succeeds and the current retrieval source map verifies.

## Evidence

The fixed real-corpus run selected 55 canonical events locally in about 0.2
seconds. Four sequential source-scoped NotebookLM calls succeeded, kept all
returned source IDs in scope, and averaged about 43.5 seconds each. That is
useful for cited synthesis but not appropriate as the default latency path.

## Consequences

- A fresh task can answer broad temporal questions without NotebookLM or a
  persistent conversation.
- Remote synthesis receives only mapper-approved current retrieval parts.
- A missing/stale local index or source map produces an explicit degraded
  result instead of an apparently complete remote answer.
- Citation scope can be checked immediately, but claim factuality requires a
  local verifier.
- Concurrency is not implied by this decision; it remains blocked behind
  conversation/source isolation and verifier gates.
