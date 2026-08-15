# PQ-005 Run Packet: Bounded executor

## Objective

Implement and test one executor boundary for sequential, packed, and future
isolated-replica work. The default must be one worker, zero implicit retries,
ordered results, checkpoint failure visibility, bounded cancellation, and no
partial-success return after an operation failure.

## Implementation

- `scripts/notebooklm_temporal_executor.py`
- `tests/test_notebooklm_temporal_executor.py`
- NLM-002 now routes its sequential case loop through this executor.

## Required invariants

- Shared mutable NotebookLM conversations cannot request concurrency above one.
- Packed mode is one remote ask, not parallelism.
- Concurrency above one requires an explicit isolated-replica proof.
- Retry budget is 0 or 1 and requires an explicit retry classifier.
- A failed operation or checkpoint raises an aggregate code; the caller never
  receives an apparently complete partial list.
- Reports remain aggregate-only and do not serialize answer or credential text.

## Verification

Run the executor unit suite, synthesis/parser/verifier suites, Python compile,
then run the real NLM-002 command against only the disposable retrieval
notebook. Do not run `--new` against the persistent chat notebook.
