# Handoff

## Current recommendation

- Compare sticky shard ownership plus local-router fan-out, then measure 60/15/5-minute freshness profiles. The hardened single-notebook release lane is complete.

## Why

- The current release gates pass and the single-notebook deployment is healthy.
- The 5x/10x experiment isolated assignment churn and fan-out as the scaling constraints.
- The radar isolates freshness and multi-notebook scale as the weakest measured axes.

## Preconditions

- Patch behavior must be covered by offline fixtures before touching the live deployment.
- Live actions must preserve auth profiles, task IDs, source lineage, and persistent CLI conversations.
- Any destructive retention or source swap must prove exact ownership and remain inside the configured projection/notebook boundary.
- GitHub release controls occur only after local and live gates pass.

## Return-to-research triggers

- Semantic candidate recall misses any required benchmark case.
- Auto-enrollment cannot preserve source headroom atomically.
- Dedicated notebook separation is unsupported by upstream behavior.
- Shorter freshness gates cause rate limits, revision storms, or retrieval regressions.
