# Quickstart

This is the shortest supported path from a fresh clone or downloaded ZIP to a usable local-first thread search setup. It does not require Git after the files are downloaded, and it never asks you to copy a credential file into the repository.

## 1. Install prerequisites

Install these on Windows:

- [Node.js](https://nodejs.org/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Codex Desktop with local task history
- A Google account with NotebookLM access

Python 3.12 is created by `uv` inside the isolated runtime. You do not need to install or activate a project virtual environment manually.

Open PowerShell in this repository and use a process-scoped execution-policy bypass if Windows blocks local scripts:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1 -CheckOnly
.\install.ps1
```

`-CheckOnly` is read-only. It verifies the checkout, PowerShell, `uv`, and Node.js without creating a runtime, installing a skill, touching authentication, or contacting NotebookLM.

The installer creates:

- `%USERPROFILE%\.codex\runtimes\notebooklm-py-0.8.0` — the pinned Python/CLI runtime;
- `%USERPROFILE%\.codex\skills\codex-notebooklm-thread-rag` — the global Codex skill; and
- `%USERPROFILE%\.codex\thread-rag` — generated configs and operational state.

The repository itself remains free of auth material, task projections, run reports, and private benchmark data.

## 2. Authenticate one profile

Use the pinned CLI through the wrapper. A normal browser login is enough for interactive work; a master login enables durable unattended refresh when the account policy allows it.

```powershell
.\scripts\notebooklm_profiles.ps1 login-personal -Account "you@example.com"
.\scripts\notebooklm_profiles.ps1 master-login-personal -Account "you@example.com"
.\scripts\notebooklm_profiles.ps1 doctor-personal
```

For a second Google account, use the `work` commands. Never paste cookies, storage state, master tokens, or OAuth values into a command, issue, log, or chat.

## 3. Create two notebooks with the CLI

The CLI is the primary human interface. Keep automated retrieval and persistent human conversation in separate notebooks:

```powershell
$NotebookLm = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\notebooklm.exe"
& $NotebookLm -p personal create "Codex Thread Retrieval" --json
& $NotebookLm -p personal create "Codex Thread Chat" --json
& $NotebookLm -p personal list --json
```

Copy the two notebook IDs from the JSON/list output. The retrieval notebook may use disposable automation conversations; the chat notebook preserves its CLI conversation history. The optional MCP server is installed as a secondary adapter, not the main interface.

## 4. Create bounded configs

Start with a small explicit set of task IDs. The safer default is capacity-aware auto-enrollment after that seed; an empty scope is rejected unless you explicitly opt into `-AllowAllThreads`.

```powershell
.\New-SyncConfig.ps1 `
  -Device "my-pc-retrieval" `
  -NotebookId "RETRIEVAL_NOTEBOOK_ID" `
  -Profile personal `
  -NotebookRole retrieval `
  -ThreadIds @("TASK_ID_1", "TASK_ID_2")

.\New-SyncConfig.ps1 `
  -Device "my-pc-chat" `
  -NotebookId "CHAT_NOTEBOOK_ID" `
  -Profile personal `
  -NotebookRole chat `
  -ThreadIds @("TASK_ID_1", "TASK_ID_2")
```

The generated JSON is stored under `%USERPROFILE%\.codex\thread-rag`; it is intentionally not a repository file. For a second account, pass `-Profile work` and verify the account mapping first.

## 5. Verify before uploading

Run the retrieval profile in dry-run mode first. This builds the local sanitized projection and temporal index, performs read-only NotebookLM checks, and does not create or replace remote sources.

```powershell
$Config = "$env:USERPROFILE\.codex\thread-rag\my-pc-retrieval\sync_config.json"
.\scripts\thread_rag_doctor.ps1 -Config $Config
.\scripts\notebooklm_thread_sync_runner.ps1 -Config $Config -DryRun
```

If the dry run is healthy, run the same command without `-DryRun` to upload the first revision, then reconcile:

```powershell
.\scripts\notebooklm_thread_sync_runner.ps1 -Config $Config
.\scripts\notebooklm_thread_sync_runner.ps1 -Config $Config -ReconcileOnly
```

## 6. Use the fastest appropriate query path

For “what was I doing yesterday?” or other exact date/time questions, use the local temporal CLI. It avoids NotebookLM conversation state and is the authoritative path for timestamps:

```powershell
$Python = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe"
& $Python .\scripts\thread_temporal_cli.py recap `
  --db "$env:USERPROFILE\.codex\thread-rag\temporal\temporal.sqlite3" `
  --expression yesterday `
  --timezone America/New_York `
  --mode standard
```

For vague semantic memory, use the NotebookLM retrieval route only after the doctor reports fresh, reconciled state. Local ThreadOps search remains the fallback and final verification authority.

## 7. Add silent scheduled upkeep (optional)

```powershell
.\scripts\install_notebooklm_thread_sync_task.ps1 `
  -Config $Config `
  -TaskName "Codex NotebookLM Thread Sync - my-pc" `
  -Minutes 15
```

The supported launcher uses `pythonw.exe` and `CREATE_NO_WINDOW`; it should not flash a console window. The task only runs while the Windows user has an interactive session. Confirm it with:

```powershell
Get-ScheduledTask -TaskName "Codex NotebookLM Thread Sync - my-pc"
```

## If something fails

1. Run `.\install.ps1 -CheckOnly` to separate missing prerequisites from application/auth problems.
2. Run the profile `doctor-*` command and inspect the newest sanitized JSON report under the configured `runs` directory.
3. Do not copy credentials from another profile or delete the retrieval/chat separation.
4. Use [RECOVERY.md](RECOVERY.md) for recovery and [SECURITY.md](../SECURITY.md) for credential boundaries.

The local install and offline tests can be green while live NotebookLM retrieval certification remains a separate evidence gate. Treat the current README deployment results as machine-specific measurements, not a guarantee for a new account or corpus.
