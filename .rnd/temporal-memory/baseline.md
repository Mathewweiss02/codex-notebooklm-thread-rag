# TM-000 Baseline Evidence

Captured: 2026-08-14

## Scope

This is an aggregate, read-only baseline. It contains no task IDs, NotebookLM IDs, account emails, message text, credentials, or raw run logs.

## Repository and runtime

- Git branch: `codex/recursive-eval-loop-publish`
- Pre-existing product changes: none detected; only the `.rnd/temporal-memory` planning workspace was untracked.
- Host Node.js: `v24.11.1`
- Host Python: `3.11.7`
- Pinned NotebookLM runtime Python: `3.12.4`
- Pinned upstream CLI: `NotebookLM CLI 0.8.0 (8fb61cb1)`
- `git diff --check`: passed

## Current automated suite

`tests/run_all.ps1` passed with exit code 0:

- 22 Node tests passed.
- 60 Python tests passed.
- 16 Python scripts compiled.
- PowerShell parse checks passed.
- Runner, doctor, profile-auth, profile-ACL, skill-install, config, and scheduler integrations passed.
- Total Python test duration: 1.738 seconds.

This is a baseline of current behavior, not a certification result. It does not cover the future temporal index, exhaustive period selection, or safe NotebookLM fan-out.

## Live local inventory

The read-only app-server inventory completed at `2026-08-14T06:18:28.430Z`:

- Visible task count: `140`.
- Aggregate sorted task-ID fingerprint: `d1167272648b9e16e87a565542d1fad83a4c57a0c2710c11a4ab75cb054893c8`.
- Registered local configs: `2` (`1` retrieval and `1` persistent chat).

The 140-task result supersedes the README's older 130-task deployment statement for this baseline. The README must be refreshed only after the new architecture has a measured, committed source of truth.

## Local semantic-search latency

Three identical read-only `thread_search.mjs --query NotebookLM --limit 1 --no-hydrate --json` runs measured:

- `1361.51 ms`
- `1315.21 ms`
- `1402.14 ms`

Observed range: `1315.21–1402.14 ms`; arithmetic mean: `1359.62 ms`. This is a warm/cold mixed baseline and is not yet a temporal-index performance target.

## Known baseline gaps

- The current date-bounded search is semantic-query-first and cannot prove exhaustive daily coverage.
- No independent temporal oracle existed before TM-000.
- No safe same-notebook parallel-chat topology is proven.
- README deployment counts are stale relative to the current app-server inventory.
