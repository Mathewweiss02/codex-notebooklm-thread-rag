# NLM-002 Result

## Fixture verification

The local parser/normalizer tests cover the supported NotebookLM JSON answer
and source-reference shapes, malformed reference entries, out-of-scope source
IDs, citation-marker detection, and non-object payload rejection.

## Live experiment

Run on 2026-08-14 against the 140-thread current retrieval deployment:

- Local temporal status: `ok`.
- Local canonical events: 55; all 55 were included in the deep context pack.
- Selected thread scope: 1 thread; mapped current source parts: 1.
- Live source mapping: `ok`.
- Cases: 4; remote successes: 4; remote errors: 0.
- Citation scope: 4/4 cases stayed inside the mapper-approved source set.
- Returned reference counts: 22, 2, 25, and 11.
- Mean remote latency: approximately 43.5 seconds per sequential case.
- Local temporal CLI latency for the same fixed boundary: approximately 0.2
  seconds.

The report at
`%USERPROFILE%\\.codex\\thread-rag\\temporal\\nlm-002-report.json` stores
only aggregate evidence and answer hashes; it is not a source of truth for
the answer content.

## Decision: ADR-004

Keep the local temporal CLI/index as the default authority for exact date,
time, count, and “when did I…” questions. Allow source-scoped NotebookLM as
an explicitly requested synthesis layer after local selection and successful
mapping. Require citation-scope validation and visible degraded/error status;
never silently substitute a remote synthesis answer for missing local
coverage.

NotebookLM adds value for multi-message synthesis and citation-formatted
explanations, but its measured latency is too high for the default exact
retrieval path. The experiment does not prove answer factuality by itself:
NLM-003 must locally verify claims against the selected event/index evidence.

## Limitations and next gate

- Four cases are a development experiment, not the sealed holdout benchmark.
- Citation scope is verified by returned source IDs; claim-to-event factual
  verification remains NLM-003.
- The experiment used one selected thread for the fixed `today` window, so it
  does not establish multi-thread synthesis quality.
- The calls were intentionally sequential; no parallel NotebookLM capacity
  or safety claim is made.

Advance to NLM-003: build the local verifier that can accept, reject, or
degrade remote temporal claims using local evidence.
