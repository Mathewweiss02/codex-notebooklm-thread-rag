# Codex NotebookLM Thread RAG

A Windows-first, incremental semantic-search layer for Codex task history. It projects only visible user/assistant messages, redacts credential-shaped content, uploads revisioned sources to NotebookLM, and keeps deterministic local ThreadOps search as the authority and fallback.

This project does **not** repair broken Codex tasks or replace Codex storage. It helps rediscover relevant tasks and facts, then requires local verification before acting.

## Proven baseline

The v4 ADS-PC evaluation used 20 varied real tasks, including renamed tasks, forks, active/archive pairs, giant histories, unrelated titles, split sources, and close decoys:

- 28,056 visible messages projected into 32 ready sources (17.18 MB).
- Zero surviving credential patterns, raw user-home paths, reasoning records, or tool payloads in the inspected projection.
- Raw NotebookLM citation-order Top-1: 18/20 (90%); candidate recall: 20/20 (100%).
- End-to-end hybrid Top-1 after authoritative local reranking: **20/20 (100%)**.
- 32/32 live source reconciliation with no missing sources, title drift, or duplicate titles.
- Both isolated auth profiles passed exact-account checks, passive live checks, browserless master-token renewal, and restricted-ACL tests.
- The installed global skill completed a scheduled v4 refresh with exit code 0; all 20 unchanged tasks were skipped without duplicate uploads.

A full-corpus production proof projected 312 closed tasks into 338 parts with the same privacy gates, uploaded them into two fresh isolated notebooks, and independently reconciled the exact live source sets: 216 tasks/240 parts and 96 tasks/98 parts. Both shards passed with zero missing, extra, duplicate, or errored sources. The larger shard retains 60-source rolling-update headroom. Running tasks remain excluded until their active turn closes.

These are machine-specific results. NotebookLM is the candidate finder; local Codex history remains the authority.

## Architecture

```text
Codex session JSONL
        |
        v
sanitized incremental projection
        |  active-turn/goal veto, then 60-minute quiet gate
        v
NotebookLM revisioned sources
        |
        v
semantic candidate task IDs + citations
        |
        v
candidate-only local reranking
        |
        v
local Codex evidence verification
        |
        +--> deterministic ThreadOps search fallback
```

The scheduler polls every 15 minutes. Unchanged tasks are skipped. A changed task normally waits until it has been quiet for 60 minutes. JSONL task-start/task-complete markers and active goal state veto projection even after the six-hour hard ceiling or an explicit force, so multi-hour reasoning runs are not captured mid-turn.

## Requirements

- Windows PowerShell 5.1 or newer.
- Node.js.
- Python 3.12.
- [`uv`](https://docs.astral.sh/uv/).
- Codex Desktop with local session history.
- A Google account with NotebookLM access.

NotebookLM-py uses undocumented Google interfaces and may temporarily break after upstream changes. Keep the local fallback.

## 1. Install

```powershell
.\install.ps1
```

This creates an isolated runtime at `%USERPROFILE%\.codex\runtimes\notebooklm-py-0.8.0`, runs the complete offline test suite, and installs the global `codex-notebooklm-thread-rag` skill under `%USERPROFILE%\.codex\skills`. It does not remove or modify an existing `nlm` installation. Upgrades preserve a rollback copy under `%USERPROFILE%\.codex\skill-backups`.

## 2. Authenticate

Normal browser auth:

```powershell
.\scripts\notebooklm_profiles.ps1 login-personal -Account "you@example.com"
```

Durable unattended auth:

```powershell
.\scripts\notebooklm_profiles.ps1 master-login-personal -Account "you@example.com"
```

For a second account, use `work` instead of `personal`. Leave the sign-in window open until the terminal reports success. Verify browserless renewal:

```powershell
.\scripts\notebooklm_profiles.ps1 refresh-personal
.\scripts\notebooklm_profiles.ps1 doctor-personal
```

The account email selects the intended Google identity; it is not a token. Never pass or save the `--oauth-token` value unless you understand its exposure risk.

## 3. Lock down credentials

Profiles live under `%USERPROFILE%\.notebooklm\profiles`. Master tokens are durable Google credentials. Restrict the selected profile directory to the Windows user and `SYSTEM`, and never commit or sync it. See [SECURITY.md](SECURITY.md).

## 4. Create a sacrificial notebook and config

Start with a small, disposable notebook and 20 varied task IDs. Create the notebook with the NotebookLM CLI, record its ID, then generate a stable registered configuration:

```powershell
.\New-SyncConfig.ps1 -Device "my-pc-eval" -NotebookId "NOTEBOOK_ID" -Profile personal -ThreadIds @(
  "THREAD_ID_1",
  "THREAD_ID_2"
)
```

The config is written under `%USERPROFILE%\.codex\thread-rag\my-pc-eval\sync_config.json` and registered in `%USERPROFILE%\.codex\thread-rag\registry.json`. Empty task scope is rejected. `-AllowAllThreads` is an explicit high-risk opt-in that must wait for source-budget planning.

After bounded shard notebooks have been created, uploaded, and exactly reconciled, generate one serialized production config:

```powershell
.\New-SyncConfig.ps1 -Device "my-pc-prod" -Profile personal `
  -AllowAllThreads -Sharded -SourceLimit 300 -Reserve 60 `
  -ShardPrefix "Codex Threads - my-pc"
```

The planner preserves existing task-to-notebook assignments. New closed tasks enter available headroom; if another shard is required but no notebook has been provisioned, the runner fails closed and drops nothing.

## 5. Dry-run, upload, and reconcile

```powershell
$Config = "$env:USERPROFILE\.codex\thread-rag\my-pc-eval\sync_config.json"
.\scripts\notebooklm_thread_sync_runner.ps1 -Config $Config -DryRun
.\scripts\notebooklm_thread_sync_runner.ps1 -Config $Config
.\scripts\notebooklm_thread_sync_runner.ps1 -Config $Config -ReconcileOnly
```

The sync uploads a new revision fully before deleting only the old source IDs already linked to that task. It refuses schema-policy drift, missing parts, size drift, oversized skipped visible messages, and lineage-mismatched deletion.

## 6. Benchmark retrieval

Create a local, gitignored `retrieval_cases.json` with vague remembered queries and expected task IDs. Then run:

```powershell
& "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe" `
  .\scripts\notebooklm_thread_retrieval_benchmark.py `
  --state "$env:USERPROFILE\.codex\thread-rag\my-pc-eval\state.json" `
  --cases .\retrieval_cases.json `
  --profile personal `
  --notebook-id NOTEBOOK_ID `
  --threshold 0
```

The live benchmark stores hashes, ranks, source IDs, and task IDs—not answer text. Raw citation order is diagnostic. Measure the actual retrieval contract by reranking its recorded candidates locally:

```powershell
& "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe" `
  .\scripts\thread_rag_hybrid_benchmark.py `
  --raw-report "PATH_TO_RAW_REPORT" `
  --cases .\retrieval_cases.json `
  --state "$env:USERPROFILE\.codex\thread-rag\my-pc-eval\state.json" `
  --out "PATH_TO_HYBRID_REPORT" `
  --threshold 0.95
```

Require 100% semantic candidate recall and at least 95% hybrid Top-1 before depending on semantic discovery.

## 7. Schedule

```powershell
.\scripts\install_notebooklm_thread_sync_task.ps1 `
  -Config "$env:USERPROFILE\.codex\thread-rag\my-pc-eval\sync_config.json" `
  -TaskName "Codex NotebookLM Thread Sync - my-pc" `
  -Minutes 15 `
  -ExecutionLimitMinutes 120
```

The task starts at logon and every 15 minutes while that Windows user has an interactive session. Runs sharing a projection root use one mutex, overlapping triggers are ignored, and a nightly read-only reconciliation validates the exact scoped source set for every shard.

## Search contract

1. Use Codex metadata/title search first.
2. If the synchronized notebook is healthy and fresh, use NotebookLM to identify cited candidate task IDs.
3. Rerank only those candidates against local Codex JSONL. The bundled semantic command does this automatically and refuses to return a usable result when local verification fails.
4. Read and verify local evidence before reporting facts or taking action.
5. If freshness, auth, reconciliation, citations, or identity is uncertain, use deterministic local ThreadOps content search.
6. For original instructions, use provenance-aware origin recovery after task discovery.

## Multiple accounts and devices

Keep `work` and `personal` profiles separate. Do not infer source limits from a subscription label; query the live limits for each account because entitlements can change. In the initial test both profiles reported tier 2, 500 notebooks, and 300 sources per notebook.

Use one stable device namespace and one bounded notebook set per computer. Cross-device search can query each device's notebooks, while every machine retains independent provenance and credentials. See [docs/MULTI_DEVICE.md](docs/MULTI_DEVICE.md).

## Current boundary

The 20-task retrieval pilot and bounded two-shard full-corpus synchronization are proven on the reference machine. Initial shard creation remains an explicit gated operation. After exact reconciliation, the serialized scheduler may incrementally maintain those provisioned shards while preserving privacy, active-turn, capacity, lineage, and exact-source gates.
