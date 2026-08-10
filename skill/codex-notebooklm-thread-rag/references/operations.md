# Operations

## Verify the upstream runtime

The isolated runtime pins `teng-lin/notebooklm-py` v0.8.0 and installs its Python API, CLI, headless-auth support, and MCP server. The CLI is the primary operator interface; MCP is optional. Verify both command surfaces before profile or sync work:

```powershell
$Runtime = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts"
& "$Runtime\notebooklm.exe" --version
& "$Runtime\notebooklm-mcp.exe" --help
```

Use `notebooklm.exe` for normal account, notebook, source, chat, research, artifact, and diagnostic operations. The MCP server reuses stored CLI profiles and does not authenticate independently. Bind an account explicitly with `notebooklm-mcp --profile personal` or `--profile work` only when an MCP host specifically requires it.

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

Use `-RefreshAuth` only when the user wants an active `auth refresh --verify` test.

## Authenticate profiles

The wrapper reserves `personal` and `work`. Inspect older upstream profiles before renaming them; rename through the CLI and never copy credential files:

```powershell
& "$Runtime\notebooklm.exe" profile list --json
& "$Runtime\notebooklm.exe" profile rename main personal
& "$Runtime\notebooklm.exe" profile rename alt work
```

Skip a rename when the destination exists or the email mapping differs. A profile is ready for scheduled synchronization only after exact-account verification, passive live auth, active `auth refresh --verify`, and restricted ACL checks. Record whether the profile also has a master token: browser-session-only Workspace profiles can rotate while valid but cannot guarantee fully unattended recovery after an administrator-enforced expiry.

```powershell
& "$Skill\scripts\notebooklm_profiles.ps1" master-login-work -Account "work@example.com"
& "$Skill\scripts\notebooklm_profiles.ps1" master-login-personal -Account "personal@example.com"
& "$Skill\scripts\notebooklm_profiles.ps1" refresh-all
& "$Skill\scripts\notebooklm_profiles.ps1" check
```

The login wrapper defaults to upstream's isolated `chromium` flow. Use `-Browser chrome` or `-Browser msedge` only when required by the account's sign-in policy. Leave the browser open until success is reported. The master-login actions verify the exact account and lock the profile directory ACL.

## Project, plan, and sync

Run the configured runner in dry-run mode first:

```powershell
& "$Skill\scripts\notebooklm_thread_sync_runner.ps1" -Config "CONFIG_PATH" -DryRun
```

Runner dry-run materializes the sanitized local projection/state and performs live read checks, but does not write NotebookLM sources. The projection CLI's lower-level `--dry-run` is only a candidate listing and intentionally writes no state.

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

Normal runner passes automatically inventory newly visible tasks when `AutoEnroll=true`. Enrollment stage-projects unknown tasks in a temporary root, reads the live source limit, and updates the explicit allowlist only when every task fits both the steady-state reserve and immediate upload cap. Diagnose or apply it directly:

```powershell
& "PYTHON_PATH" "$Skill\scripts\notebooklm_thread_enroll.py" --config "CONFIG_PATH"
& "PYTHON_PATH" "$Skill\scripts\notebooklm_thread_enroll.py" --config "CONFIG_PATH" --apply
```

Use separate configs and projection roots for `NotebookRole=retrieval` and `NotebookRole=chat`. The retrieval notebook is disposable automation state. The chat notebook is the primary persistent CLI conversation surface and is never selected by automatic semantic search.

## Semantic discovery

```powershell
& "PYTHON_PATH" "$Skill\scripts\notebooklm_thread_search.py" "vague remembered description"
```

The command discovers only registered retrieval configs, refuses stale/unmonitored instances by default, verifies all state-linked sources live, rejects unrelated extras in strict mode, resets only a notebook explicitly marked as disposable retrieval chat, and returns locally reranked candidate task IDs without answer text. Treat `--no-local-rerank` as a diagnostic switch only.

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

The scheduler uses a per-config mutex, ignores overlapping starts, has a 120-minute execution limit by default, waits 60 minutes after recent task activity, applies a six-hour hard freshness ceiling to previously projected changing tasks, and performs daily strict source reconciliation. A 60-minute quiet gate is eventual freshness, not real-time freshness.

## Retention

Retention is dry-run-first and exact-root constrained:

```powershell
& "PYTHON_PATH" "$Skill\scripts\thread_rag_retention.py" --root "PROJECTION_ROOT" --search-root "SEARCH_RUNS_ROOT"
```

Review the report before `--apply` or setting `RetentionApply=true`. Current parts, previous lineage, and the configured revision floor remain protected.

## Recovery

- Authentication failure: stop sync, run passive check, then refresh or recapture only the affected profile.
- Interrupted upload: rerun the same config; do not delete partial ready sources manually.
- Reconciliation failure: inspect current state-linked source IDs/titles; repair missing current parts before guarded deletion.
- Repository relocation: registered configs point to globally installed skill scripts, not the clone. Re-run the installer to upgrade the skill.
- NotebookLM outage: use `thread_search.mjs` and `thread_origin.mjs` locally.
