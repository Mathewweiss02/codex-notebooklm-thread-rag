# Decision Packet

## Mission

- Codex NotebookLM Thread RAG Ultra Instinct Program

## Current state

- Confirmed: The live deployment currently reconciles 130 visible tasks to 132 unique live sources with no missing or untracked sources.
- Confirmed: The current branch contains governed recursive-evaluation tooling and sealed holdout evidence on top of the published operational-hardening release.
- Confirmed: The doctor now rejects stale runner success timestamps and parses NotebookLM auth JSON status instead of trusting exit code zero.
- Suspected bottleneck: The largest immediate bottleneck is acceptance/ranking generalization: candidate recall passed holdout-v2, while Top-1 and false-positive gates failed.
- Suspected bottleneck: The first-fit planner preserves task locality and reserve capacity, but stateless full replanning causes 64.62% shared-assignment churn at 5x and 83.08% at 10x; sticky ownership is the scaling bottleneck.
- Suspected bottleneck: The largest UX bottleneck is multiple low-level scripts without a single CLI-first lifecycle command.

## Surviving options

### rnd-014: Improve acceptance and ranking generalization
- Branch: acceptance-ranking-generalization
- Score: 38.0
- Next lane: `research-experiment-runner`
- Why it survives: high current rank with actionable status `queued`

### rnd-007: Compare local router plus NotebookLM fan-out
- Branch: scale-architecture
- Score: 33.5
- Next lane: `research`
- Why it survives: high current rank with actionable status `queued`

### rnd-004: Measure and optimize freshness profiles
- Branch: freshness-throughput
- Score: 33.0
- Next lane: `research`
- Why it survives: high current rank with actionable status `queued`

## Recommendation

- Chosen path: `rnd-014` - Improve acceptance and ranking generalization
- Why it wins now: Selected because it is actionable now with score 38.0 and strong leverage/uncertainty reduction.
- What would change the decision: stronger evidence, a new blocker, or a higher-leverage upstream item.

## Pruning decisions

- Drop: naive 50-candidate fusion and stateless full-corpus reshuffling; both regressed measured quality or scaling stability.
- Park: freshness tuning, local-router fan-out, source-content integrity, parser resilience, auth cadence, and multi-device failover until retrieval generalization passes.
- Merge: bounded semantic retry, local-authority verification, duplicate-title consensus, and governed benchmark tooling remain one coherent baseline for the next experiment.

## Next lane

- Recommended lane: `research-experiment-runner`
- Handoff note: Treat the operational hardening and benchmark-integrity lanes as complete, but do not merge the recursive retrieval branch yet. Resume with a development-only acceptance/ranking experiment, then author a new sealed holdout and require three consecutive passing frozen runs.
