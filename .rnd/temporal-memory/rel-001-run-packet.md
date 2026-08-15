# REL-001 Run Packet — Shadow Refresh and Retrieval Canary

## Objective

Prove that the canonical projection state, local temporal handoff, SQLite
index, scheduler runner, and dedicated retrieval NotebookLM source mapping can
operate together without changing the persistent CLI-chat notebook.

## Safety boundary

- Stage the temporal manifest, source snapshots, handoff, and SQLite index before
  promotion.
- Do not reset or query the persistent chat notebook through automation.
- Do not create isolated replica notebooks; PQ-006 remains approval-gated.
- Emit aggregate counts, statuses, and digests only in retained evidence.

## Required checks

1. Fresh state-to-handoff shadow replay into a temporary directory.
2. Temporary SQLite integrity and digest verification.
3. Production index/handoff digest parity after promotion.
4. Retrieval-profile runner dry run containing the temporal-refresh step.
5. One live retrieval-profile runner pass with auth, projection, temporal
   refresh, source sync, and retention steps.
6. Live source mapping with zero missing, stale, mismatched, or untracked
   retrieval sources.
7. Doctor checks for both profiles, including console-free scheduler behavior.

## Rollback boundary

If any required check fails, retain the prior temporal index/handoff and do not
promote NotebookLM or replica state. The temporal refresh helper preserves the
last verified SQLite state on staging, policy, source, or diagnostic failure.
