# NLM-001 Run Packet

## Mission

Map selected local Codex thread IDs to current ready retrieval NotebookLM
source parts without selecting or mutating the persistent CLI-chat notebook.

## Safety boundary

- Read local projection state and verify the shared redaction policy.
- Require `NotebookRole=retrieval` and `DisposableSearchChat=true`.
- Require `uploadRevision == revision`, a ready current part, a local projected
  file, and matching local content digest.
- Exclude `previousSources` from the remote mapping.
- Optionally list live NotebookLM sources read-only and compare exact source IDs
  and titles.
- Return `degraded` for missing/stale mapping; `--strict` converts that state to
  a nonzero exit. Never delete, create, rename, or reset a source/conversation.

## Method

1. Run fixture unit tests for ready mapping, missing thread, local drift, and
   chat-role rejection.
2. Map one live retrieval thread locally.
3. Map all current retrieval threads and run a read-only live source listing.
4. Record aggregate counts only; do not place raw auth or session data in the
   R&D packet.

## Reproducibility commands

```powershell
$python = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe"
& $python -m unittest tests.test_notebooklm_temporal_source_map -v
& $python scripts\notebooklm_temporal_source_map.py --config "RETRIEVAL_CONFIG" --context-pack "CONTEXT_PACK" --live-verify --strict
```

The live command requires an explicitly selected retrieval config or context
pack; it must never discover the chat config as a fallback.
