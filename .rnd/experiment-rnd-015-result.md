# Experiment Result

## Experiment

- ID: `rnd-015`
- Title: Measure NotebookLM query concurrency and personal latency
- Status: partial evidence; throughput hypothesis supported, production promotion failed

## What was run

- Inspected `notebooklm-py` v0.8.0 transport concurrency, retry middleware, and notebook/conversation locks.
- Ran four visible development-match questions through the disposable retrieval notebook at pack sizes 2 and 4. Every ask started from a reset sacrificial conversation; persistent chat was not touched and no semantic retry was used.
- Added answer-text-free citation diagnostics, marker-first section mapping, and candidate-only local reranking.
- Measured local temporal search with explicit local-day bounds and the new `--today` shortcut.
- Added and unit-tested a `--fast` remote mode that performs one semantic ask with zero automatic HTTP 429/5xx retries.

## Evidence

- Cached individual baseline for the same four questions: 4/4 candidate hits, 4/4 Top-1, 285.09 seconds total.
- Initial pack-size-2 result: 100.55 seconds, 2.3869 questions/minute, 1/4 mapped expected tasks.
- Initial pack-size-4 result: 47.63 seconds, 5.0386 questions/minute, 2/4 mapped expected tasks.
- Diagnostic pack-size-4 result before marker-first mapping: 57.91 seconds, 4/4 globally retrieved expected tasks, 3/4 per-section candidate hits, and 2/4 raw Top-1.
- Marker-first pack-size-4 result: 50.49 seconds remote, 4/4 globally retrieved expected tasks, 4/4 per-section candidate hits, and 3/4 raw Top-1. Offline local reranking took 2.56 seconds and remained 3/4, for about 53.05 seconds end to end and roughly 5.37x speedup over four individual asks.
- The remaining Q4 error was not source omission: the correct task was semantic rank 2 with local score 73.05 and coverage 0.829, while the wrong semantic-rank-1 candidate scored 42.36 with coverage 0.487. Existing near-tie policy kept semantic rank 1 and then correctly abstained for insufficient evidence. This belongs to `rnd-014`; it was not tuned here.
- Five warmed local date-filtered scans measured 1.518–1.642 seconds (P50 1.543 seconds). A natural-language `--today` query found two prior tasks with timestamped evidence in 3.03 seconds while excluding the current task.
- Private reports remain gitignored and retain hashes, IDs, metrics, and mappings without question or answer text.

## Result

- Prompt packing is a credible throughput technique, but four questions are far too small for promotion and Top-1 remains below the frozen quality gate.
- Marker-first citation mapping fixed most apparent section loss; raw candidate recall reached 4/4. The remaining failure is acceptance/ranking, not global NotebookLM retrieval.
- Naive same-notebook concurrent asks are rejected: the upstream client serializes them, and bypassing its local lock with processes would race the server's mutable current conversation.
- Safe true parallelism requires distinct existing conversation IDs or distinct notebook replicas. The public client does not expose non-destructive conversation-pool provisioning, so replicas require explicit authorization.
- Local temporal lookup and explicit no-retry controls are safe incremental UX wins, now implemented and tested.

## Next move

- Keep `rnd-015` active until the single-query fast/balanced latency comparison and a sufficiently varied development batch are measured.
- Do not run 16/50 packed questions until `rnd-014` resolves the observed related-candidate ranking failure or the quality gate is otherwise restored.
- Provision isolated notebook replicas only after explicit approval, then ramp 1/2/4 workers with conversation-integrity and throttling checks before considering 8.
