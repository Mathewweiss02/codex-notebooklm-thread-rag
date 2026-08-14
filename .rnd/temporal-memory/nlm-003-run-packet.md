# NLM-003 Run Packet

## Mission

Prevent a successful NotebookLM CLI call from being promoted as factual when
its citations, time claims, conversation state, or local evidence cannot be
verified.

## Safety boundary

- Verify the complete local context pack before evaluating remote prose.
- Verify current retrieval source IDs and projection-file digests.
- Check only answer-linked citation markers for claim evidence, while still
  rejecting any out-of-scope returned source.
- Reject follow-up responses because they could inherit conversation history.
- Reject explicit dates/timestamps outside the resolved local period.
- Keep answer text and cited passages in memory only; emit aggregate verdicts
  and hashes.

## Method

1. Run fixture tests for accepted evidence, incomplete local coverage, wrong
   day, out-of-scope sources, marker mismatch, follow-up state, structural
   citations, projection support, and projection digest drift.
2. Rerun the NLM-002 four-case sequential disposable-notebook experiment with
   the verifier wired into the in-memory response boundary.
3. Record remote transport success separately from factual promotion.
4. Keep the local temporal CLI as the deterministic fallback when verification
   abstains.

## Reproducibility commands

```powershell
$python = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe"
& $python -m unittest tests.test_notebooklm_temporal_verify -v
& $python scripts/notebooklm_temporal_verify.py `
  --context-pack CONTEXT_PACK_JSON `
  --source-map SOURCE_MAP_JSON `
  --response RESPONSE_JSON
```

The standalone verifier exits nonzero for `degraded`, `abstained`, or
`error`; callers must not convert those states to successful remote answers.
