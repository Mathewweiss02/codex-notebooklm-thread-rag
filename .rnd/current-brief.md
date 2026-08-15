# Current Brief

## Mission

- Codex NotebookLM Thread RAG Ultra Instinct Program

## Current state

- Improved but not closed: bounded retry produced one 32/32 candidate-recall and 32/32 Top-1 development run, but the first fresh sealed holdout failed at 30/32 hybrid Top-1 and 1/8 false positives.
- Confirmed bottleneck: bounded retry succeeded on accuracy but invoked 15 retries and raised remote latency to 65.95s P50 / 147.62s P95.
- Confirmed bottleneck: holdout-v2 reached 32/32 semantic candidate recall but only 30/32 hybrid Top-1 with 1/8 false positives; acceptance/ranking generalization, especially negative rejection, is now the main retrieval bottleneck.
- Confirmed constraint: naive 50-candidate fusion reaches 100% union recall but lowers final ranking quality and is rejected.
- Confirmed throughput signal: four packed questions reached 4/4 candidate recall in 50.49 seconds remote and about 53.05 seconds with local reranking, roughly 5.37x faster than four cached individual asks; accepted Top-1 remained 3/4, so promotion is blocked.
- Confirmed concurrency constraint: same-notebook independent asks are serialized by the client, while process-level bypass would race mutable server conversation state. Safe true parallelism needs isolated notebook replicas or pre-existing independent conversation IDs.
- Confirmed UX increment: local `--today` returns timestamped evidence, and remote `--fast` now enforces one semantic ask with no 429/5xx retry middleware.
- Fresh local baseline on the current 145-thread projection recovered all 32/32 development positives at candidate depth 80 with zero local-search errors; this strengthens local candidate selection but is not remote semantic or hybrid quality proof.
- The controlled offline threshold sweep did not produce a safe promotion candidate: stricter local gates removed the observed false positive only by causing substantial positive abstention, so ranking/acceptance needs a more discriminating signal rather than a blunt threshold.
- The latest one-case live source-scoped smoke still hit the NotebookLM rate-limit circuit breaker; no new remote quality evidence was counted.
- Suspected bottleneck: The largest immediate bottleneck is validation: several important properties work but are not continuously proven.
- Suspected bottleneck: The first-fit planner preserves task locality and reserve capacity, but stateless full replanning causes 64.62% shared-assignment churn at 5x and 83.08% at 10x; sticky ownership is the scaling bottleneck.
- Suspected bottleneck: The largest UX bottleneck is multiple low-level scripts without a single CLI-first lifecycle command.

## Queue status

- Total items: 15
- done: 7
- active: 1
- queued: 7

## Next actionable item

- ID: `rnd-015`
- Title: Measure NotebookLM query concurrency and personal latency
- Branch: query-concurrency-latency
- Next lane: `research-experiment-runner`
- Reason: Prompt packing shows large speed potential but failed the Top-1 gate on a tiny sample. Finish fast/balanced latency measurement and restore ranking quality before scaling the batch suite or provisioning replicas.

## Recommended next lane

- Keep holdout-v2 sealed. Resolve the development-only related-candidate ranking failure in `rnd-014`, compare `--fast` and balanced single-query latency on the same queries, then run a larger packed development sample. Provision isolated replicas only with explicit approval and ramp 1/2/4 before 8.
