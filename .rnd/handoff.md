# Handoff

## Current recommendation

- Treat the operational hardening and benchmark-integrity lanes as complete, but do not merge the recursive retrieval branch yet. Resume with a development-only acceptance/ranking experiment, then author a new sealed holdout and require three consecutive passing frozen runs.

## Why

- The live single-notebook deployment is operationally healthy and reconciled.
- Holdout-v2 reached 32/32 semantic candidate recall, proving candidate discovery is no longer the immediate accuracy bottleneck.
- Hybrid Top-1 reached only 30/32 and false-positive rate reached 1/8, so retrieval-generalization release gates do not pass.
- The 5x/10x experiment still isolates assignment churn and fan-out as later scaling constraints, but those are downstream of the current ranking/rejection gap.

## Preconditions

- Patch behavior must be covered by offline fixtures before touching the live deployment.
- Live actions must preserve auth profiles, task IDs, source lineage, and persistent CLI conversations.
- Any destructive retention or source swap must prove exact ownership and remain inside the configured projection/notebook boundary.
- GitHub release controls occur only after local and live gates pass.
- Holdout-v2 is spent and diagnostic-only; do not inspect or tune against its case details.

## Branch decisions

- Keep: bounded semantic retry, local-authority verification, duplicate-title consensus, and the governed benchmark tooling.
- Park: freshness tuning, sticky multi-notebook routing, source-content integrity, parser resilience, auth cadence, and multi-device failover until retrieval generalization passes.
- Drop: naive 50-candidate fusion and stateless full-corpus reshuffling.

## Return-to-research triggers

- Semantic candidate recall misses any required benchmark case.
- A development policy cannot improve rejection/ranking without regressing the 24-case regression or 12-case sibling gates.
- Auto-enrollment cannot preserve source headroom atomically.
- Dedicated notebook separation is unsupported by upstream behavior.
- Shorter freshness gates cause rate limits, revision storms, or retrieval regressions.
