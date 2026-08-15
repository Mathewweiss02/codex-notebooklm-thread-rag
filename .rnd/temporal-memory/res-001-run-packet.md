# RES-001 Run Packet: Failure and recovery gate

## Objective

Verify that corruption, incomplete handoff, stale state, auth-error JSON,
source drift, cancellation, and operation/checkpoint failures produce explicit
failure or abstention rather than silent success.

## Evidence

- Focused temporal index corruption/rollback tests.
- Extractor incomplete-source and oversized-line tests.
- Doctor stale-runner and auth-status tests.
- NotebookLM source-scope and claim-verifier negative tests.
- Bounded executor failure, cancellation, retry, and checkpoint tests.
- Full repository integration suite.
