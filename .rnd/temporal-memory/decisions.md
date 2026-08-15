# Temporal Memory Decisions

## 2026-08-14 — TM-001 contract approval

### Approved

- Local Codex history is the temporal authority.
- Timestamp membership is message-level, UTC-stored, explicit-timezone interpreted, and half-open.
- Unsupported or invalid timestamps are quarantined rather than guessed.
- Active/archive duplicates collapse by stable content identity while forks remain distinct.
- Temporal selection is complete before semantic ranking or NotebookLM synthesis.
- Context packs expose coverage and omissions instead of silently truncating.
- NotebookLM is source-scoped synthesis only; local verification is mandatory.
- Persistent chat and disposable retrieval are separate roles.
- Default remote concurrency is one until an isolation topology earns promotion.
- Errors, stale success, and remote failures cannot masquerade as empty or successful results.

### Deferred empirical choices

- `TM-002`: index engine/content boundary.
- `TM-006`: activity segmentation threshold; accepted as `activity-segmentation-v1` with a strict `gap > 60 minutes` boundary and no midnight-only split.
- `PQ-001`–`PQ-004`: packing and conversation isolation topology.

### Reversal conditions

Any contract is revisited if a certification-matrix case demonstrates that it cannot preserve canonical identity, complete period membership, local verification, persistent-chat integrity, or recoverability.
