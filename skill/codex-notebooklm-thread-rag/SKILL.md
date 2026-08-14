---
name: codex-notebooklm-thread-rag
description: "Operate the installed Codex-to-NotebookLM thread retrieval system: diagnose profiles and schedulers; build sanitized incremental projections; plan source-safe notebook shards; synchronize and reconcile revisioned sources; search vaguely remembered Codex conversations semantically; verify cited task IDs against local authoritative history; recover original instructions; and fall back to deterministic local content search. Use when a user wants to find prior Codex tasks or facts, check or repair thread-RAG freshness, configure another computer/account, benchmark retrieval, or safely maintain this synchronization stack."
---

# Codex NotebookLM Thread RAG

Use NotebookLM as a semantic candidate finder and local Codex history as the authority. Never report a remembered fact or mutate a task solely from NotebookLM prose.

## Upstream boundary

This skill operates a wrapper around `teng-lin/notebooklm-py` v0.8.0. Treat the upstream `notebooklm` CLI as the primary operator interface. The package also supplies `NotebookLMClient`, the optional secondary `notebooklm-mcp` adapter, profile storage, and master-token recovery. This repository supplies sanitized Codex projection, a local timestamp-preserving temporal index, guarded synchronization, local reranking/verification, scheduling, and recovery policy. Read `references/operations.md` before setup or auth work; use the CLI for general NotebookLM operations outside thread retrieval.

## Locate the installation

Set the skill root without assuming the repository location:

```powershell
$CodexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$Skill = Join-Path $CodexRoot "skills\codex-notebooklm-thread-rag"
$Registry = Join-Path $CodexRoot "thread-rag\registry.json"
```

Read `references/operations.md` for setup, synchronization, search, and recovery commands. Read `references/release-gates.md` before expanding scope, adding a device, or publishing a release.

Read `references/temporal-memory.md` when the user asks what they did during a
date/time period, when an event occurred, to compare periods, or to load a
chronological working context. That route is local-first and does not require
NotebookLM.

## Find a remembered task

1. If the request is broad temporal intent—“what was I doing yesterday,” “what did I work on last week,” “when did I ask for this,” “show today,” or “compare Tuesday and Wednesday”—invoke `scripts/thread_temporal_cli.py` first. Use `when` to disclose the range, `recap`/`context` for the evidence pack, `find` for exact lexical matching inside the period, and `compare` for separate period deltas. Do not route these requests to semantic-only NotebookLM search.
2. If the clue is an exact task title or ID without broad temporal intent, inspect Codex task metadata/title search first.
3. If the clue is vague semantic memory without an exhaustive period request, run `scripts/thread_rag_doctor.ps1` against the registered configuration. Require a recent successful runner and reconciled live sources before NotebookLM.
4. Run `scripts/notebooklm_thread_search.py` with the user's remembered description only for the semantic candidate-finding route. For an ordinary latency-sensitive lookup, pass `--fast`; do not silently retry if it fails. Use the balanced default only when the user requests higher confidence or the task justifies retry latency. The command requires cited candidate task IDs and reranks them against authoritative local JSONL by default. The dedicated RAG notebook must declare `NotebookRole=retrieval` and `DisposableSearchChat=true`; resetting its chat prevents cross-query contamination. Registered `NotebookRole=chat` configs are excluded from automated search so persistent CLI conversation history is never erased.
5. Require `locallyVerified=true` on a selected semantic candidate, then inspect bounded local evidence. Use `scripts/thread_search.mjs --thread ID` for focused verification and `scripts/thread_origin.mjs` when the user needs the original instruction rather than a later recap.
6. If the temporal index is missing or stale, report the explicit local diagnostic and bootstrap/rebuild it; do not silently downgrade an exhaustive temporal request to semantic search. If semantic auth, freshness, reconciliation, citations, or identity is uncertain, skip NotebookLM and use deterministic local search directly.
7. Relay only relevant, credential-redacted evidence. Distinguish original request, later clarification, and downstream summary.

The stable cold-start route table is `references/temporal-routing.json`; its
examples are evaluated by the repository test suite.

Use `--project PROJECT_LABEL_OR_HASH` on temporal `recap`, `context`, `find`,
or `compare` commands when the question is workspace-scoped. The filter uses
path-free manifest metadata and fails closed when metadata is missing. Context
signals are conservative heuristic navigation hints with event-level
provenance, not independent factual claims.

## Synchronize safely

1. Run the projection first. Permit only policy `visible-messages-secrets-redacted-v4`.
2. Review errors, visible-message overflow, source count, and the shard plan before upload.
3. For retrieval configurations, refresh the temporal handoff and SQLite index from the same stable projection snapshot before any remote sync. A failed or diagnostically unsafe refresh leaves the last verified derived state intact; it never silently falls back to a stale temporal index.
4. Upload new revision parts fully and verify them live before deleting any previous source.
5. Delete only source IDs recorded in that task's `previousSources` with an exact live title match.
6. Run `--validate-only` reconciliation after changes.
7. Keep `AllowAllThreads=false`. Use `notebooklm_thread_enroll.py` to stage-project newly visible tasks, query live source limits, prove rolling-update headroom, and atomically extend the explicit scope.
8. Treat `RejectUntrackedSources=true` as mandatory for dedicated notebooks. Report extras; never delete them automatically.
9. Apply retention only through `thread_rag_retention.py` after reviewing its dry-run report. Current and previous lineage must remain protected.
10. Use `thread_temporal_rollback.py --dry-run --root TEMPORAL_ROOT` to inspect
    a matched previous handoff/index generation before rollback. Rollback is
    derived-state only and must not alter canonical Codex sessions.

## Parallel querying (experimental)

Same-notebook fan-out is unsafe because the NotebookLM conversation is mutable.
Use `notebooklm_isolated_ramp.py` for a dry-run capacity plan first. It rejects
the persistent `chat` profile, never copies source IDs into a replica, and
keeps live reports aggregate-only:

```powershell
& "$PythonPath" "$Skill\scripts\notebooklm_isolated_ramp.py" `
  --config "$env:USERPROFILE\.codex\thread-rag\ads-pc-pilot\sync_config.json" `
  --pool-sizes 1 2 4 8 16 32 50 `
  --out "$env:USERPROFILE\.codex\thread-rag\temporal\isolated-ramp-dry-run.json"
```

Live creation and querying require both `--apply` and
`--confirm-isolated-retrieval-replicas`. Start with one control or two
replicas, use a bounded case limit, and run `--cleanup` only when the evidence
has been retained. Advance only after source fingerprints, citation scope,
local verification, conversation isolation, rate limits, cancellation, and
resource checks pass at the prior level. Fifty is an experiment ceiling, never
the default path.

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
- Remote outage, expired auth, timeout, HTTP 429, and HTTP 5xx failures may use
  the deterministic local fallback. Label that result as local/degraded; never
  count it as raw remote retrieval quality.
- Any isolated-replica executor must use an explicit rate-limit classifier and
  the bounded adaptive limiter; a mock backoff result is not a live canary.
- Never delete raw Codex sessions, source emails/files, unrelated NotebookLM sources, or auth profiles as part of recovery.
