# Handoff

## Current recommendation

- Move the confirmed release-critical branch into implementation while keeping scale, freshness, and architecture alternatives in research.

## Why

- The immediate defects are concrete, reproducible, and have clear acceptance signals.
- The broader architecture questions lack comparative evidence and should not block correctness fixes.
- The benchmark is both a release gate and the evidence foundation for future architecture comparisons and radar scores.

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
