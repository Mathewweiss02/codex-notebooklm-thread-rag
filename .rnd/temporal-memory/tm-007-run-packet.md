# TM-007 Run Packet

## Mission

Implement a hierarchical context packer that turns an exhaustive temporal
selection into navigable period/day/activity/message evidence while making
budget loss, provenance, and drill-down behavior explicit.

## Invariants under test

- The SQLite index is the only canonical event source.
- The complete half-open period is selected before segmentation or budgeting.
- Full selected-thread history is used to keep a segment identity stable when a
  query starts at midnight or inside an existing activity.
- Local-day labels use the already-tested Node ICU timezone boundary; the
  pinned Windows Python runtime is not assumed to contain `tzdata`.
- Budgets never silently truncate: every omitted event and omission reason is
  exposed in coverage and segment/day metadata.
- Drill-down narrows to one exact segment and retains the parent period count;
  intentional scope narrowing is not reported as a failed/degraded result.
- The pack contains no generated factual claims and every included message
  retains event identity, digest, role, timestamp, and source lineage.

## Synthetic fixture

The focused fixture contains 7 sanitized events across 2 threads, 4 measured
activities, 3 New York local dates, a cross-midnight activity, and an event
outside a subset query that proves full-history segment identity.

## Method

1. Build a temporary SQLite index through the existing handoff/index contract.
2. Run the context packer at the full standard budget.
3. Run a subset beginning inside an activity and compare its segment ID with the
   full-period result.
4. Run a two-message budget and verify every omitted event is accounted for.
5. Run segment drill-down and an equal-boundary empty period.
6. Exercise stale resolver metadata and invalid timezone rejection.
7. Run the full repository suite and Python compilation.

## Reproducibility commands

```powershell
$python = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe"
& $python -m unittest tests.test_thread_temporal_context -v
node --test tests/thread_temporal_localize.test.mjs
& .\tests\run_all.ps1
```

## Stop condition

Do not promote the packer if any selected event is missing, any out-of-window
event appears, an omission lacks a reason/handle, or drill-down changes the
parent segment identity.
