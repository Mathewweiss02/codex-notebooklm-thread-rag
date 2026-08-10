---
name: codex-notebooklm-thread-rag
description: "Operate the installed Codex-to-NotebookLM thread retrieval system: diagnose profiles and schedulers; build sanitized incremental projections; plan source-safe notebook shards; synchronize and reconcile revisioned sources; search vaguely remembered Codex conversations semantically; verify cited task IDs against local authoritative history; recover original instructions; and fall back to deterministic local content search. Use when a user wants to find prior Codex tasks or facts, check or repair thread-RAG freshness, configure another computer/account, benchmark retrieval, or safely maintain this synchronization stack."
---

# Codex NotebookLM Thread RAG

Use NotebookLM as a semantic candidate finder and local Codex history as the authority. Never report a remembered fact or mutate a task solely from NotebookLM prose.

## Upstream boundary

This skill operates a wrapper around `teng-lin/notebooklm-py` v0.8.0. Treat the upstream `notebooklm` CLI as the primary operator interface. The package also supplies `NotebookLMClient`, the optional secondary `notebooklm-mcp` adapter, profile storage, and master-token recovery. This repository supplies sanitized Codex projection, guarded synchronization, local reranking/verification, scheduling, and recovery policy. Read `references/operations.md` before setup or auth work; use the CLI for general NotebookLM operations outside thread retrieval.

## Locate the installation

Set the skill root without assuming the repository location:

```powershell
$CodexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$Skill = Join-Path $CodexRoot "skills\codex-notebooklm-thread-rag"
$Registry = Join-Path $CodexRoot "thread-rag\registry.json"
```

Read `references/operations.md` for setup, synchronization, search, and recovery commands. Read `references/release-gates.md` before expanding scope, adding a device, or publishing a release.

## Find a remembered task

1. Inspect Codex task metadata/title search first when the clue is exact.
2. Run `scripts/thread_rag_doctor.ps1` against the registered configuration. Require a recent successful runner and reconciled live sources.
3. Run `scripts/notebooklm_thread_search.py` with the user's remembered description. It requires cited candidate task IDs and reranks them against authoritative local JSONL by default. The dedicated RAG notebook must declare `NotebookRole=retrieval` and `DisposableSearchChat=true`; resetting its chat prevents cross-query contamination. Registered `NotebookRole=chat` configs are excluded from automated search so persistent CLI conversation history is never erased.
4. Require `locallyVerified=true` on the selected candidate, then inspect bounded local evidence. Use `scripts/thread_search.mjs --thread ID` for focused verification and `scripts/thread_origin.mjs` when the user needs the original instruction rather than a later recap.
5. If semantic auth, freshness, reconciliation, citations, or identity is uncertain, skip NotebookLM and use the deterministic local search directly.
6. Relay only relevant, credential-redacted evidence. Distinguish original request, later clarification, and downstream summary.

## Synchronize safely

1. Run the projection first. Permit only policy `visible-messages-secrets-redacted-v4`.
2. Review errors, visible-message overflow, source count, and the shard plan before upload.
3. Upload new revision parts fully and verify them live before deleting any previous source.
4. Delete only source IDs recorded in that task's `previousSources` with an exact live title match.
5. Run `--validate-only` reconciliation after changes.
6. Keep `AllowAllThreads=false`. Use `notebooklm_thread_enroll.py` to stage-project newly visible tasks, query live source limits, prove rolling-update headroom, and atomically extend the explicit scope.
7. Treat `RejectUntrackedSources=true` as mandatory for dedicated notebooks. Report extras; never delete them automatically.
8. Apply retention only through `thread_rag_retention.py` after reviewing its dry-run report. Current and previous lineage must remain protected.

## Authentication boundary

- Keep `work` and `personal` profiles separate and verify the exact account after login.
- Use `--fresh` for every interactive account capture.
- Treat `master_token.json` as a durable Google credential. Never print, copy into chat, commit, or sync it.
- Restrict profile ACLs to the intended Windows user and `SYSTEM`.
- Use passive auth checks for health probes. Use `auth refresh --verify` only when renewal is intended; it rotates a valid browser session and can fall back to a master token when one exists.

## Failure behavior

- Stop uploads on policy drift, oversized skipped visible messages, missing files, source-cap failure, stale revision, account mismatch, or lineage mismatch.
- Rerun an interrupted upload: accepted source IDs are checkpointed and exact-title ready sources are reused.
- Keep the deterministic local search operational when NotebookLM or its unofficial interface is unavailable.
- Never delete raw Codex sessions, source emails/files, unrelated NotebookLM sources, or auth profiles as part of recovery.
