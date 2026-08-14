# PERF-001 Run Packet: Local temporal performance

## Objective

Measure the current local temporal CLI on supported broad and narrow period
expressions without printing or persisting message content. Compare standard
and deep context budgets and identify the real bottleneck before optimizing.

## Method

- Real temporal SQLite index and fixed `now=2026-08-14T08:00:00.000Z`.
- Timezone: `America/New_York`.
- Supported expressions: today, yesterday, last week, week to date, past 24
  hours, and an explicit date.
- Standard: 3 repetitions per expression.
- Deep: 2 repetitions per expression.
- One large-budget week-to-date control used 10,000 messages and 1,000,000
  characters to distinguish CPU latency from context-budget omission.

Only status, coverage counts, and latency aggregates are retained.
