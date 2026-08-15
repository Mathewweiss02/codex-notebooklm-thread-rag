# PQ-001 Run Packet: Temporal prompt-packing development gate

## Objective

Freeze a CLI-aligned prompt-packing surface before any live throughput claim.
The packet tests stable question batching, redaction, answer-section parsing,
marker-first citation-to-section mapping, source-scope accounting, and
fail-closed handling for malformed structure.

## Boundaries

- This is an offline structural experiment.
- It does not call NotebookLM, mutate a notebook, or create a conversation.
- It does not use or tune against the VAL-001 holdout details.
- It does not authorize same-notebook concurrency.
- The local temporal selector and claim verifier remain authoritative.

## Inputs

- Fixture: `fixtures/temporal-pack-development.json`
- Contract: `temporal-prompt-pack-contract-v1.json`
- Cases: 16 across broad temporal, exact-when, comparison, synthesis,
  activity-boundary, timestamp, negative-control, and format-control classes.

## Commands

```powershell
$python = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe"
& $python -m unittest tests.test_notebooklm_temporal_pack_benchmark -v
& $python scripts/notebooklm_temporal_pack_benchmark.py `
  --cases .rnd\temporal-memory\fixtures\temporal-pack-development.json `
  --expression "development temporal scope" `
  --timezone America/New_York `
  --pack-sizes 1 2 4 8 `
  --out "$env:USERPROFILE\.codex\thread-rag\temporal\pq-001-pack-plan.json"
```

Run the benchmark twice and compare `promptPlanSha256` and `suiteDigest`.
Only aggregate counts, digests, and per-pack metadata are written to the
result artifact; prompt and answer text remain out of the report.

## Gate

Pass requires all structural tests to pass, every case to produce a non-empty
redaction-aware prompt, all requested pack sizes to be represented, and the
repeated plan digests to match. A pass is not a claim about NotebookLM answer
quality, remote latency, citation support, or concurrency safety.

## Next decision

After this gate, inspect the installed CLI's conversation lifecycle and prove
whether explicit independent conversation pools are non-destructive. Keep
`--new` retrieval asks isolated from the persistent user chat.
