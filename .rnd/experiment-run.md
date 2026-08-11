# Experiment Run Packet

## Mission

- Codex NotebookLM Thread RAG Ultra Instinct Program

## Chosen experiment

- ID: `rnd-013`
- Title: Prove benchmark integrity before recursive optimization
- Why now: highest-priority actionable experiment with score 41.5

## Hypothesis

- A versioned suite with frozen regression, visible development, adversarial, negative/no-match, temporal/freshness, and sealed holdout cases can distinguish genuine retrieval improvement from benchmark memorization or label drift.

## Variable

- Evaluation split, query stratum, acceptable-answer set, abstention policy, and holdout exposure

## Metric or evidence

- Case/schema integrity, semantic candidate recall, hybrid Top-1, false-positive rate, false-negative rate, Wilson confidence intervals, latency percentiles, and three-run stability

## Method

- Freeze the existing 24 cases as regression-only; create independently adjudicated development and sealed-holdout manifests; hash every frozen input and label artifact; run visible cases for diagnosis but reveal holdout aggregates only; preserve immutable raw reports and an adjudication ledger; reject any change that targets case IDs or weakens non-retrieval gates.

## Stop condition

- Do not optimize production retrieval until the suite passes integrity audit. Stop for user review after three honest experiment rounds without statistically meaningful improvement, or immediately on holdout leakage, post-score relabeling, dropped hard cases, unsafe live behavior, rate-limit risk, or a safety/CI/chat/reconciliation regression.

## Recommended next lane

- `validation`
