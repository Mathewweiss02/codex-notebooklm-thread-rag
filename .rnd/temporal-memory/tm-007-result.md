# TM-007 Result

## Implementation

- Added `thread_temporal_context.py` for period, local-day, activity-segment,
  and message-evidence packing.
- Added `query_thread_events` to the SQLite boundary so activity identity can be
  computed from full selected-thread history without duplicating SQL elsewhere.
- Added `thread_temporal_localize.mjs`, a one-shot Node ICU bridge for local-day
  labels and timezone validation; this avoids assuming unavailable Python
  `tzdata` on Windows.
- Added stable segment IDs, explicit brief/standard/deep budgets, balanced
  round-robin allocation, omission accounting, source lineage, empty results,
  stale-range rejection, and scoped drill-down output.

## Focused evidence

| Case | Result |
| --- | --- |
| Full 7-event period | 7/7 included, 4 segments, 3 local days, 0 out-of-window events |
| Query starts inside an existing activity | Segment ID matches full-history result; `truncatedBefore=true` is explicit |
| Two-message budget | 2 included, 5 omitted, all omissions reported as `message-budget` |
| Cross-midnight activity | One segment retains both local dates without a midnight-only split |
| Segment drill-down | Exact segment scope, parent period count retained, status `ok`, no identity change |
| Equal start/end | Honest `empty` result with zero events |
| Stale resolver metadata | Rejected with `INVALID_RANGE_METADATA` |
| Invalid timezone | Rejected at the ICU boundary with `INVALID_TIMEZONE` |

## Verification

- Focused context tests: 4 passed.
- Focused local-day tests: 2 passed.
- Full repository suite after TM-007 additions: 34 Node tests and 67 Python
  tests passed; Python compilation, PowerShell parsing, runner/doctor/profile/
  ACL/install/config/scheduler integrations all passed.

## Decision

Accept `temporal-context-pack-v1` and `context-pack-policy-v1.json` as the
implementation boundary for the next unified CLI step. Keep the packer local
and evidence-only; NotebookLM synthesis and claim verification remain separate
later lanes.

## Limitations

- Budget values are transparent starting defaults, not a claim of optimal user
  experience; giant-corpus scale and monotonic brief/standard/deep replay remain
  validation work.
- The packer is not yet the single user-facing command; TM-008 must integrate
  resolver → index → packer and provide stable human/JSON output.
- Real private-corpus extractor-to-index replay, process-kill/disk-full tests,
  and remote source-scoped synthesis remain open release gates.

## Next move

Advance to TM-008: build the unified local temporal CLI with `recap`, `when`,
`find`, `compare`, `context`, diagnostics, and explicit local-only fallback.
