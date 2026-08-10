# Experiment Run Packet

## Mission

- Codex NotebookLM Thread RAG Ultra Instinct Program

## Chosen experiment

- ID: `rnd-006`
- Title: Simulate 2x, 5x, and 10x corpus capacity
- Why now: highest-priority actionable experiment with score 39.5

## Hypothesis

- Deterministic sharding preserves complete-task locality and update headroom at larger scale.

## Variable

- Corpus multiplier and part distribution

## Metric or evidence

- Shard count, fan-out, headroom, rebalance churn

## Method

- Replicate the observed 130-task/132-part distribution at 1x, 2x, 5x, and 10x.
- Run the production first-fit planner with a 300-source limit and 60-source rolling reserve.
- Measure shard count, shard loads, minimum/average headroom, broadcast fan-out, and the percentage of shared task assignments that move between scale steps.
- Treat complete-task locality and minimum headroom as hard safety constraints.

## Stop condition

- Escalate architecture when broadcast fan-out exceeds three notebooks or when more than 10% of existing task assignments move during a scale step.

## Recommended next lane

- `research-synthesis-and-decision`: compare sticky shard assignment and local-router fan-out strategies because the current stateless replan crosses the churn budget at 5x.
