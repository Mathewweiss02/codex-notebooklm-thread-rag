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

Runner dry-run materializes the sanitized local projection/state, refreshes a temporary temporal handoff/index when `TemporalRefresh=true`, and performs live read checks, but does not write NotebookLM sources. The temporal refresh is staged and verified before promotion; malformed source diagnostics, missing sessions, or index mismatches fail closed. The projection CLI's lower-level `--dry-run` is only a candidate listing and intentionally writes no state.

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

Use separate configs and projection roots for `NotebookRole=retrieval` and `NotebookRole=chat`. The retrieval notebook is disposable automation state and normally has `TemporalRefresh=true`. The chat notebook is the primary persistent CLI conversation surface, keeps `TemporalRefresh=false`, and is never selected by automatic semantic search.

The runner's temporal step uses the pinned Node and Python runtimes, copies each canonical session to a stable staging area, extracts timestamped visible messages, builds the derived SQLite index transactionally, and verifies handoff/index digests after promotion. The production handoff keeps one `.previous` copy for recovery. The current index is a derived cache: rebuilding or removing it never removes canonical Codex sessions.

Refresh promotion is serialized by a recoverable SQLite lock around the staged
handoff/index pair, so overlapping runs cannot publish different generations
as a mixed pair. Schema version 1 migrates in place to version 2 with a
migration ledger. To inspect or restore the previous verified pair:

```powershell
& "PYTHON_PATH" "$Skill\scripts\thread_temporal_rollback.py" --root "$env:USERPROFILE\.codex\thread-rag\temporal" --dry-run
& "PYTHON_PATH" "$Skill\scripts\thread_temporal_rollback.py" --root "$env:USERPROFILE\.codex\thread-rag\temporal"
```

Rollback changes only derived temporal artifacts and verifies matching handoff
and index digests; it does not modify canonical session data.

## Semantic discovery

```powershell
& "PYTHON_PATH" "$Skill\scripts\notebooklm_thread_search.py" "vague remembered description" --fast
```

The command discovers only registered retrieval configs, refuses stale/unmonitored instances by default, verifies all state-linked sources live, rejects unrelated extras in strict mode, resets only a notebook explicitly marked as disposable retrieval chat, and returns locally reranked candidate task IDs without answer text. `--fast` uses one semantic attempt and disables automatic 429/5xx transport retries; omit it when reliability warrants the balanced retry policy. Treat `--no-local-rerank` as a diagnostic switch only.

The standalone temporal source mapper prints an aggregate report by default;
raw source/thread identifiers are available only with the explicit
`--include-identifiers` diagnostic switch. In-memory callers used by the
source-scoped synthesis experiment retain the identifiers only inside the
local verification boundary.

Any future isolated-replica executor must provide an explicit rate-limit
classifier. The bounded executor's adaptive limiter honors a capped
`Retry-After` value, applies capped exponential backoff, and stops after a
finite rate-limit event budget. Ordinary failures are never silently treated as
throttling, and deterministic mock evidence does not substitute for a live
canary.

Verify locally:

```powershell
node "$Skill\scripts\thread_search.mjs" --query "same remembered clues" --thread "CANDIDATE_ID" --json
& "PYTHON_PATH" "$Skill\scripts\thread_temporal_cli.py" recap --db "$env:USERPROFILE\.codex\thread-rag\temporal\temporal.sqlite3" --expression yesterday --timezone America/New_York
node "$Skill\scripts\thread_origin.mjs" --thread "THREAD_ID" --query "original instruction clues" --json
```

For broad date/time requests use the temporal CLI before any semantic ask:
`when`, `recap`, `context`, `find`, and `compare` are local-only exact-time
commands. Pass `--project PROJECT_LABEL_OR_HASH` for an exact workspace filter.
The older `thread_search.mjs --today` path remains a low-level
diagnostic/focused search surface, not the primary temporal route.

Benchmark a recorded live run without paying for another NotebookLM pass:

```powershell
& "PYTHON_PATH" "$Skill\scripts\thread_rag_hybrid_benchmark.py" --raw-report "RAW_REPORT" --cases "CASES_JSON" --state "PROJECTION_ROOT\state.json" --out "HYBRID_REPORT" --threshold 0.95
```

## Schedule

```powershell
& "$Skill\scripts\install_notebooklm_thread_sync_task.ps1" -Config "CONFIG_PATH" -TaskName "Codex NotebookLM Thread Sync - DEVICE" -Minutes 15
```

The scheduler uses the configured runtime's `pythonw.exe` plus Windows' `CREATE_NO_WINDOW` process flag, so recurring syncs do not open or flash a terminal. Task Scheduler's `Hidden` setting only controls whether the task appears in its own UI and is not a substitute for the console-free launcher. The scheduler uses a per-config mutex, ignores overlapping starts, preserves the runner's exit code, has a 120-minute execution limit by default, waits 60 minutes after recent task activity, applies a six-hour hard freshness ceiling to previously projected changing tasks, refreshes the retrieval temporal index as part of the same run, and performs daily strict source reconciliation. A 60-minute quiet gate is eventual freshness, not real-time freshness.

## Retention

Retention is dry-run-first and exact-root constrained:

```powershell
& "PYTHON_PATH" "$Skill\scripts\thread_rag_retention.py" --root "PROJECTION_ROOT" --search-root "SEARCH_RUNS_ROOT"
```

Review the report before `--apply` or setting `RetentionApply=true`. Current parts, previous lineage, and the configured revision floor remain protected. The runner's aggregate-only `ProjectionRoot\soak-evidence` records are append-only and explicitly outside retention deletion; use them for the 168-hour resource-aware soak monitor.

```powershell
& "PYTHON_PATH" "$Skill\scripts\thread_temporal_release_monitor.py" `
  --evidence-root "PROJECTION_ROOT\soak-evidence" `
  --out "$Repo\.rnd\temporal-memory\resource-soak-monitor.json" `
  --minimum-hours 168 `
  --max-gap-hours 2 `
  --require-resource
```

## Recovery

- Authentication failure: stop sync, run passive check, then refresh or recapture only the affected profile.
- Interrupted upload: rerun the same config; do not delete partial ready sources manually.
- Reconciliation failure: inspect current state-linked source IDs/titles; repair missing current parts before guarded deletion.
- Temporal index failure: inspect the aggregate refresh code, verify the last-good SQLite index, and rerun the documented refresh after the projection source is stable. Do not delete canonical sessions or manually replace the handoff.
- Repository relocation: registered configs point to globally installed skill scripts, not the clone. Re-run the installer to upgrade the skill.
- NotebookLM outage: use `thread_search.mjs` and `thread_origin.mjs` locally.
- NotebookLM outage, expired auth, timeout, HTTP 429, or HTTP 5xx: the semantic
  wrapper may return a locally verified degraded candidate. Keep it labeled
  local/degraded and do not count it as raw remote retrieval quality.
