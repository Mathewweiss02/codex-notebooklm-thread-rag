# Operations

## Diagnose

List registered configurations:

```powershell
Get-Content -Raw -LiteralPath "$env:USERPROFILE\.codex\thread-rag\registry.json" | ConvertFrom-Json
```

Run offline checks, then opt into passive live auth and source reconciliation:

```powershell
& "$Skill\scripts\thread_rag_doctor.ps1" -Config "CONFIG_PATH"
& "$Skill\scripts\thread_rag_doctor.ps1" -Config "CONFIG_PATH" -Live -TaskName "SCHEDULED_TASK_NAME"
```

When `-TaskName` is omitted, the doctor auto-discovers a single scheduled task whose action references the exact config path. An explicitly supplied wrong or disabled task is a failed health check.

Use `-RefreshAuth` only when the user wants an active master-token renewal test.

## Authenticate profiles

```powershell
& "$Skill\scripts\notebooklm_profiles.ps1" master-login-work -Account "work@example.com"
& "$Skill\scripts\notebooklm_profiles.ps1" master-login-personal -Account "personal@example.com"
& "$Skill\scripts\notebooklm_profiles.ps1" refresh-all
& "$Skill\scripts\notebooklm_profiles.ps1" check
```

Leave the browser open until success is reported. The master-login actions verify the exact account and lock the profile directory ACL.

## Project, plan, and sync

Run the configured runner in dry-run mode first:

```powershell
& "$Skill\scripts\notebooklm_thread_sync_runner.ps1" -Config "CONFIG_PATH" -DryRun
```

Plan full-corpus shards after projection and before enabling all threads:

```powershell
& "PYTHON_PATH" "$Skill\scripts\notebooklm_thread_plan.py" --state "PROJECTION_ROOT\state.json" --source-limit 300 --reserve 60
```

Keep every task in one shard. The planner increases reserve to at least the largest task's part count so a rolling revision can coexist with its old sources.

Run one bounded sync and reconcile:

```powershell
& "$Skill\scripts\notebooklm_thread_sync_runner.ps1" -Config "CONFIG_PATH"
& "$Skill\scripts\notebooklm_thread_sync_runner.ps1" -Config "CONFIG_PATH" -ReconcileOnly
```

## Semantic discovery

```powershell
& "PYTHON_PATH" "$Skill\scripts\notebooklm_thread_search.py" "vague remembered description"
```

The command discovers registered configs, refuses stale/unmonitored instances by default, verifies all state-linked sources live, resets only a notebook explicitly marked as disposable chat, and returns locally reranked candidate task IDs without answer text. Treat `--no-local-rerank` as a diagnostic switch only.

Verify locally:

```powershell
node "$Skill\scripts\thread_search.mjs" --query "same remembered clues" --thread "CANDIDATE_ID" --json
node "$Skill\scripts\thread_origin.mjs" --thread "THREAD_ID" --query "original instruction clues" --json
```

Benchmark a recorded live run without paying for another NotebookLM pass:

```powershell
& "PYTHON_PATH" "$Skill\scripts\thread_rag_hybrid_benchmark.py" --raw-report "RAW_REPORT" --cases "CASES_JSON" --state "PROJECTION_ROOT\state.json" --out "HYBRID_REPORT" --threshold 0.95
```

## Schedule

```powershell
& "$Skill\scripts\install_notebooklm_thread_sync_task.ps1" -Config "CONFIG_PATH" -TaskName "Codex NotebookLM Thread Sync - DEVICE" -Minutes 15
```

The scheduler uses a per-config mutex, ignores overlapping starts, waits 60 minutes after recent task activity by default, applies a six-hour hard freshness ceiling to previously projected changing tasks, and performs daily source reconciliation.

## Recovery

- Authentication failure: stop sync, run passive check, then refresh or recapture only the affected profile.
- Interrupted upload: rerun the same config; do not delete partial ready sources manually.
- Reconciliation failure: inspect current state-linked source IDs/titles; repair missing current parts before guarded deletion.
- Repository relocation: registered configs point to globally installed skill scripts, not the clone. Re-run the installer to upgrade the skill.
- NotebookLM outage: use `thread_search.mjs` and `thread_origin.mjs` locally.
