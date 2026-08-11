# Release and scope gates

Require all applicable gates before expanding a pilot or publishing a release.

## Installation

- Isolated pinned runtime installs from a clean Codex root.
- Global skill installs, validates, upgrades with a rollback backup, and works after repository relocation.
- Config is stored under the stable Codex state root and registered once.
- Empty task scope fails unless `AllowAllThreads=true` is explicit.
- Locked dependency synchronization succeeds from `uv.lock`; hash-enforced vulnerability audit reports no unresolved critical findings.

## Projection

- Sanitizer, path removal, visible-role filtering, compaction exclusion, and deterministic splitting tests pass.
- Fixture integration proves initial projection, unchanged no-op, renamed/updated revision, and prior-source lineage preservation.
- Real-corpus scan reports no surviving credential patterns, raw home paths, reasoning, or tool payloads.
- Any oversized skipped visible-message line blocks upload.

## Synchronization

- Mock tests prove cap boundaries, resumable interrupted uploads, stable retain-old mode, post-upload verification, guarded swaps, and lineage-mismatch refusal.
- Runner tests prove benign stderr handling, nonzero failure logs, overlap skipping, reconciliation-only behavior, and empty-scope refusal.
- Live pilot reconciliation has no missing source IDs, title drift, or duplicate titles.
- Dedicated notebook reconciliation has no untracked extra sources.
- Capacity-aware enrollment either enrolls every newly visible task or refuses the entire update with an explicit capacity/projection reason.
- Retention dry-run and apply fixtures preserve current and previous lineage and reject paths outside guarded roots.

## Authentication

- Each profile is bound to the intended account.
- Passive live auth check passes.
- Health checks parse JSON `status=ok`; exit code zero alone is insufficient.
- `auth refresh --verify` passes without exposing values.
- For a profile that requires fully unattended recovery, browserless master-token re-mint also passes; document any Workspace profile that blocks master-token exchange.
- Profile ACL contains only the intended user and `SYSTEM` full-control principals.

## Retrieval

- Keep the legacy 20+ case suite as frozen regression evidence; do not treat saturation as proof of generalization.
- Use a versioned development suite and a separately authored sealed holdout with at least 40 cases, including at least 8 negative/no-match cases plus misleading titles, forks, active/archive copies, giant/split histories, sibling-equivalent labels, and related-topic decoys.
- Hash the normalized suite, query surface, labels, and corpus fingerprint before execution. Preserve raw, hybrid, and score reports in immutable evidence outside operational retention.
- The benchmark command explicitly confirms that its target is a disposable retrieval notebook; persistent CLI chat notebooks are separate.
- Record raw NotebookLM candidate recall separately from any local or union candidate surface; do not rename union recall as semantic recall.
- Require 100% semantic candidate recall and record raw citation-order Top-1 separately.
- Require at least 97.5% end-to-end hybrid Top-1 after candidate-only local reranking, at most 5% false positives, and at most 5% false negatives.
- Require three consecutive frozen threshold-passing runs and a fresh unspent holdout after the final retrieval-policy change.
- Suppress holdout case details. Aggregate holdout evidence may guide the next development stratum, but the exposed holdout is then spent and cannot prove the final release.
- Verify the winning candidate locally; maintain deterministic fallback and exact-title/near-duplicate regressions.

## Full corpus and multiple devices

- Query live account source limits; never infer them from marketing subscription names.
- Generate a deterministic shard plan with rolling-update reserve.
- Create and validate shards one at a time. Do not silently drop tasks or split one task across notebooks.
- Keep credentials/config/state local per computer. Share source notebooks, not auth directories.

## Publication

- Secret/private-identifier scan passes across tracked files and Git history.
- Working tree is clean; tests and skill validation pass from the committed revision.
- README documents unofficial NotebookLM interface risk, disposable chat behavior, local authority, and rollback.
- Pull-request CI runs once per update, actions are immutable-SHA pinned, and `main` protection requires the Windows test/audit job.
- Do not publish tokens, account emails, notebook IDs, task IDs, private queries, projections, or run logs.
