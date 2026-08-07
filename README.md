# Codex NotebookLM Thread RAG

A Windows-first, incremental semantic-search layer for Codex task history. It projects only visible user/assistant messages, redacts credential-shaped content, uploads revisioned sources to NotebookLM, and keeps deterministic local ThreadOps search as the authority and fallback.

This project does **not** repair broken Codex tasks or replace Codex storage. It helps rediscover relevant tasks and facts, then requires local verification before acting.

## Proven baseline

The initial ADS-PC evaluation used 20 varied tasks, including renamed tasks, forks, active/archive pairs, giant histories, unrelated titles, and split sources:

- 28,043 visible messages projected into 32 sources (about 17.18 MB).
- Zero surviving credential patterns, raw user-home paths, reasoning records, or tool payloads in the current projection.
- 19/20 Top-1 semantic retrieval: **95%**, meeting the acceptance gate.
- 32/32 live source reconciliation with no missing, mismatched, or duplicate titles.
- A 15-minute Windows Scheduled Task burn-in completed with exit code 0.

These are machine-specific results. NotebookLM is used for candidate discovery, never as the sole source of truth.

## Architecture

```text
Codex session JSONL
        |
        v
sanitized incremental projection
        |  60-minute quiet gate / 6-hour hard ceiling
        v
NotebookLM revisioned sources
        |
        v
semantic candidate task IDs + citations
        |
        v
local Codex task verification
        |
        +--> deterministic ThreadOps search fallback
```

The scheduler polls every 15 minutes. Unchanged tasks are skipped. A changed task normally waits until it has been quiet for 60 minutes; a previously projected task still changing for six hours becomes eligible at the hard ceiling.

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

This creates an isolated runtime at `%USERPROFILE%\.codex\runtimes\notebooklm-py-0.8.0`. It does not remove or modify an existing `nlm` installation.

## 2. Authenticate

Normal browser auth:

```powershell
.\scripts\notebooklm_profiles.ps1 login-personal
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

Start with a small, disposable notebook and 20 varied task IDs. Create the notebook with the NotebookLM CLI, record its ID, then generate local configuration:

```powershell
.\New-SyncConfig.ps1 -Device "my-pc-eval" -NotebookId "NOTEBOOK_ID" -Profile personal -ThreadIds @(
  "THREAD_ID_1",
  "THREAD_ID_2"
)
```

`config.local.json` is gitignored. An empty `ThreadIds` array means all visible tasks; do not enable that until source-budget planning is complete.

## 5. Dry-run, upload, and reconcile

```powershell
.\scripts\notebooklm_thread_sync_runner.ps1 -Config .\config.local.json -DryRun
.\scripts\notebooklm_thread_sync_runner.ps1 -Config .\config.local.json
.\scripts\notebooklm_thread_sync_runner.ps1 -Config .\config.local.json -ReconcileOnly
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
  --threshold 0.95
```

The benchmark stores hashes, ranks, source IDs, and task IDs—not answer text. Require at least 95% Top-1 before depending on semantic discovery.

## 7. Schedule

```powershell
.\scripts\install_notebooklm_thread_sync_task.ps1 `
  -Config .\config.local.json `
  -TaskName "Codex NotebookLM Thread Sync - my-pc" `
  -Minutes 15
```

The task runs only while that Windows user has an interactive session. Runs are mutex-protected, and a nightly read-only reconciliation validates every state-linked source ID and title.

## Search contract

1. Use Codex metadata/title search first.
2. If the synchronized notebook is healthy and fresh, use NotebookLM to identify candidate task IDs and require citations.
3. Read and verify the cited task locally before reporting facts or taking action.
4. If freshness, auth, reconciliation, citations, or identity is uncertain, use deterministic local ThreadOps content search.
5. For original instructions, use provenance-aware origin recovery after task discovery.

## Multiple accounts and devices

Keep `work` and `personal` profiles separate. Do not infer source limits from a subscription label; query the live limits for each account because entitlements can change. In the initial test both profiles reported tier 2, 500 notebooks, and 300 sources per notebook.

Use one stable device namespace and preferably one notebook per computer. Cross-device search can query both notebooks, while each machine retains independent provenance and credentials. See [docs/MULTI_DEVICE.md](docs/MULTI_DEVICE.md).

## Current boundary

The 20-task burn-in is ready. Full-corpus rollout is intentionally not automatic: hundreds of tasks plus split giant histories can exceed a notebook's source budget. Plan sharding/packing first, then promote in bounded batches with the same validation gates.
