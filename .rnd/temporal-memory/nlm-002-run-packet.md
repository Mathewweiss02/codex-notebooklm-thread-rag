# NLM-002 Run Packet

## Mission

Measure whether source-scoped NotebookLM synthesis adds useful, properly
cited answers after the local temporal layer has selected an exact date/time
scope.

## Safety boundary

- The local temporal CLI resolves the range, selects canonical events, and
  supplies the thread scope first.
- The source mapper must return `status=ok` and current ready retrieval parts;
  otherwise the remote step is rejected.
- Every NotebookLM call is sequential and explicitly uses the disposable
  retrieval notebook with `ask --new --yes --json`.
- The persistent CLI-chat notebook is never selected or reset.
- Prompts are passed through the shared remote redaction contract.
- The report stores no answer text, raw CLI output, credentials, cookies, or
  paths; it stores aggregate counts, hashes, latency, and citation-scope
  results.

## Method

1. Build a deep local context pack for the fixed real-corpus expression
   `today`, using `America/New_York` and a fixed `now` boundary.
2. Map the selected thread IDs to current retrieval source parts and run a
   read-only live source check.
3. Submit four varied synthesis prompts sequentially to the disposable
   retrieval notebook, each with the same mapper-approved source set.
4. Record answer/reference counts, citation scope, marker presence, latency,
   and local coverage. Never treat a remote answer as locally verified truth.
5. Decide whether NotebookLM is an optional synthesis layer or a default
   retrieval path based on measured usefulness, scope correctness, and latency.

## Reproducibility command

```powershell
$python = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe"
& $python scripts/notebooklm_temporal_synthesis_compare.py `
  --db "$env:USERPROFILE\.codex\thread-rag\temporal\temporal.sqlite3" `
  --config "$env:USERPROFILE\.codex\thread-rag\ads-pc-pilot\sync_config.json" `
  --case-file ".rnd\temporal-memory\fixtures\nlm-002-cases.json" `
  --expression today --timezone America/New_York `
  --now 2026-08-14T08:00:00.000Z `
  --out "$env:USERPROFILE\.codex\thread-rag\temporal\nlm-002-report.json" `
  --confirm-disposable-retrieval-notebook
```

The command is intentionally sequential. Concurrency remains a later,
isolation-gated experiment.
