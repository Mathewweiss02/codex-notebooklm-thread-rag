# PERF-001 Result

## Local latency

- Standard: 18/18 runs exited cleanly; overall P50 approximately 202 ms and
  P95 approximately 738 ms.
- Deep: 12/12 runs exited cleanly; overall P50 approximately 203 ms and P95
  approximately 797 ms.
- Today and past-24-hours deep selections were complete and approximately
  200–204 ms P50; empty periods completed in approximately 2 ms.
- The local path is therefore sub-second for the measured real corpus; remote
  NotebookLM synthesis remains the dominant latency surface at roughly 40
  seconds per sequential case.

## Budget finding

The default deep budget returned 504/1,017 week-to-date events and marked the
pack degraded. Raising the explicit budget to 10,000 messages/1,000,000
characters returned 1,017/1,017 events in approximately 831 ms. This is an
honest coverage-budget boundary, not a CPU bottleneck; the CLI correctly
reports degradation instead of claiming an exhaustive pack.

## Decision

Accept PERF-001 as a baseline. Do not optimize the local index prematurely.
The next quality-of-life improvement is an explicit adaptive/large-period
context mode or guided drill-down, not hidden truncation or a larger default
that could overload downstream NotebookLM prompts.
