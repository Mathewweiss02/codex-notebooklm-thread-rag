# PQ-005 Result

## Offline executor gate

- Executor tests: 8/8 passed.
- Covered ordered sequential results, unsafe shared-conversation rejection,
  packed-mode rejection of parallel workers, approved isolated-worker bounds,
  operation failure, checkpoint failure, exact retry budget, and explicit retry
  classification.
- Synthesis/parser/verifier tests: 21/21 passed in the focused run.
- Python compilation passed for the executor, synthesis runner, replica model,
  and pack benchmark.

## Real end-to-end checkpoint

The executor-integrated NLM-002 rerun used the pinned CLI and disposable
retrieval notebook only:

- Local temporal status: `ok`; canonical/included events: 55/55.
- Current mapped source parts: 1.
- Remote transport: 4/4 successes; 0 remote errors.
- Citation scope: 4/4 valid.
- Mean sequential remote latency: approximately 40.1 seconds per case.
- Claim verifier: 0/4 promoted and 4/4 abstained; no remote prose was accepted
  as local truth.

This is a clean transport/executor result and an intentional negative claim-
verification result. It does not justify raising concurrency.

## Decision

Accept PQ-005. The safe executor boundary is implemented and wired into the
current sequential remote path. PQ-006 remains gated: no live 2/4/8 ramp is
authorized until isolated replicas are explicitly approved and independently
verified.
