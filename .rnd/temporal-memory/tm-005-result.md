# TM-005 Result

## What was built

- Added `scripts/thread_temporal_resolve.mjs` using the Node runtime's ICU IANA timezone database.
- Added deterministic support for today, yesterday, tomorrow, rolling hours/days, last week, week-to-date, explicit local dates, and explicit half-open ranges.
- Added fixed-now replay, machine-readable UTC/local bounds, duration, future indication, and boundary disclosure.
- Added detection that rejects ambiguous repeated local times without an offset and nonexistent spring-gap local times.
- Preserved zero-length empty periods at exact local midnight.

## Evidence

- Full suite passed: 32 Node tests and 64 Python tests.
- Resolver tests passed 6/6 focused groups, including 23-hour spring-forward and 25-hour fall-back days.
- The pinned Python runtime's `zoneinfo` could not load IANA data on Windows because `tzdata` is absent; the resolver therefore uses already-present Node ICU instead of adding an unverified runtime dependency.

## Result

The TM-005 hypothesis is strengthened. Supported natural periods now resolve to explicit, DST-safe UTC half-open ranges without guessing through ambiguous or nonexistent local times.

## Limitations

- The resolver is not yet wired into a user-facing temporal CLI.
- Week semantics, phrase grammar, and timezone results still need integration with index queries and context packing.
- OS/ICU timezone database version is an operational input and must be recorded in release diagnostics.

## Next move

Advance `TM-005` to done and run `TM-006`: measure deterministic activity segmentation thresholds against the canonical temporal oracle before building context packs.
