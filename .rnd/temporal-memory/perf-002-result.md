# PERF-007/008/009 Result - Synthetic Scale Correctness

## Gate

The local scale harness generated synthetic events only and compared every
SQLite query result with an independent in-memory event oracle. Multipliers
1, 2, 5, and 10 used 12, 24, 60, and 120 threads respectively, with eight
events per thread and three repeated queries per scale.

- 96, 192, 480, and 960 events indexed exactly;
- every repeated query returned the full oracle set at every scale;
- no event identity or count mismatch occurred;
- the retained JSON report contains aggregate timings, allocation peaks, and
  result digests without source text or local paths.

Observed query P50 increased from approximately 2.4 ms at 1x to 10.6 ms at
10x in this bounded synthetic run. That is a slope measurement, not a
production capacity guarantee; the live corpus and NotebookLM remote path
still need separate operational limits.

## Decision

Accept the synthetic correctness/scale gate for the local index. Keep PERF-010
through PERF-012 open until a resource-aware repeated-query and wall-clock
observation packet is retained.

Evidence: `perf-002-scale-report.json`.
