# Experiment Result

## Experiment

- ID: `rnd-006`
- Title: Simulate 2x, 5x, and 10x corpus capacity

## What was run

- Replayed the production planner over synthetic 1x, 2x, 5x, and 10x corpora derived from the observed 130-task/132-part distribution.
- Held the NotebookLM source limit at 300 and the rolling-revision reserve at 60.
- Compared assignment stability only for task identities shared with the preceding scale.

## Evidence

- 1x: 130 tasks, 132 parts, 1 shard at 132 sources, 168 minimum headroom.
- 2x: 260 tasks, 264 parts, 2 shards loaded 240/24, 60 minimum headroom, 2-way fan-out, 9.23% shared-task assignment churn.
- 5x: 650 tasks, 660 parts, 3 shards loaded 240/240/180, 60 minimum headroom, 3-way fan-out, 64.62% churn.
- 10x: 1,300 tasks, 1,320 parts, 6 shards loaded 240/240/240/240/240/120, 60 minimum headroom, 6-way fan-out, 83.08% churn.
- Complete-task locality and the rolling reserve held in every scenario.

## Result

- Partially supported. Deterministic first-fit sharding preserves task locality and update headroom, but stateless full replanning is not assignment-stable as the corpus grows.
- The experiment crossed the 10% rebalance-churn budget at 5x and the three-notebook fan-out budget at 10x.
- Capacity is therefore not the first failure mode; reassignment churn and query routing are.

## Next move

- Preserve shard ownership in a registry and place only new or oversized tasks instead of recomputing all bins.
- Run `rnd-007` to compare local routing plus selective NotebookLM fan-out against broadcast search, with candidate recall as the non-negotiable gate.
- Do not migrate live data to multiple notebooks until sticky ownership, migration rollback, and router-recall fixtures pass.
