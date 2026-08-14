# NLM-003 Result

## Fixture verification

- 9 verifier tests passed.
- Covered complete local acceptance, projection-text support, projection
  digest drift, incomplete selection, wrong-day literals, out-of-scope source
  IDs, marker mismatch, follow-up state, and structural/no-text citations.
- Malformed source and response paths fail closed without exposing payload
  content.

## Live verification

The final NLM-002 rerun on 2026-08-14 used the verifier in memory:

- Remote CLI transport: 4/4 succeeded.
- Current source scope: 4/4 valid.
- Current local projection attached for verification: 1 part.
- Answer-linked claim verdicts: 0/4 accepted; 4/4 abstained with
  `CITATION_EVIDENCE_UNMATCHED`.
- Mean sequential remote latency: approximately 34.1 seconds per case.
- No answer text or cited passage was written to the report.

This is a useful negative result, not a failed safety gate: the remote model
returned structurally valid answers and source IDs, but the exact passages
attached to the answer-linked citations were not locally matchable under the
current prompt/output contract. The system therefore refuses to promote those
answers and preserves the local fallback.

## Decision

Accept `temporal-claim-verifier-v1` as the promotion boundary. NotebookLM
transport success and source-scope validity are not sufficient for factual
acceptance. Future prompt-packing work may improve evidence-friendly answer
formatting, but it must pass this verifier rather than weakening it.

## Next gate

Advance to `VAL-001`: materialize development, sealed validation, and holdout
temporal cases before optimizing prompt packing or testing concurrency.
