# Codex NotebookLM Thread RAG Ultra Instinct Program

## Goal

Turn the current working CLI-first Codex-to-NotebookLM retrieval system into an evidence-driven, self-enrolling, recoverable, capacity-aware system whose quality can be measured across every important axis. Preserve NotebookLM as the current semantic backbone while continuously testing whether any architectural seam has a materially better option.

## Desired outcome

- A trustworthy release that fixes every confirmed audit defect.
- A live deployment that enrolls new visible tasks safely and reports when capacity prevents enrollment.
- Persistent human CLI conversations isolated from disposable automated retrieval chats.
- A repeatable 20+ case benchmark and a measured radar scorecard.
- A ranked long-term research queue for freshness, scale, accuracy, resilience, privacy, cost, and operability.

## Non-goals

- Do not expose credentials, private task IDs, raw session files, or NotebookLM IDs in Git.
- Do not delete unrelated NotebookLM sources or local files outside guarded lineage and retention rules.
- Do not replace NotebookLM merely because another architecture is fashionable; alternatives must win measured comparisons.
- Do not pretend an unmeasured axis is maxed out.

## Success signals

- Health checks reject stale runner state and JSON auth failures.
- Every newly visible eligible task is enrolled or produces an explicit capacity/error decision.
- Dedicated retrieval notebooks reject untracked sources and never erase persistent CLI chat history.
- At least 20 varied cases achieve 100% semantic candidate recall and at least 95% hybrid Top-1.
- Retention is bounded, recoverable, dry-run-first, and lineage-aware.
- CI runs once per PR update, dependencies are reproducible, and the release is protected and tagged.
- Every radar axis has a metric, evidence timestamp, confidence level, target, and stop condition.

## Current biggest unknown

Whether the present NotebookLM semantic-candidate plus local deterministic rerank architecture keeps its accuracy, latency, and source-capacity advantages as the corpus and update rate grow by an order of magnitude.

## Phases

- [x] Mission framing
- [x] System mapping
- [x] Broad bottleneck discovery
- [x] Initial experiment design
- [x] Queue prioritization
- [ ] Release-critical implementation and validation
- [ ] Live 20+ case benchmark
- [ ] Live migration and release
- [ ] Wide architecture experiments
- [ ] Evidence-backed radar scorecard iteration
