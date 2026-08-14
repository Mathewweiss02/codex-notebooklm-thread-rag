# PQ-007 Result - Live Packed Retrieval Experiment

## Evidence

The safe packed topology was exercised against the disposable retrieval
notebook at sizes 1, 2, 4, and 8. It issued one remote ask per batch and kept
the persistent CLI-chat notebook untouched.

- Pack 1: 4/4 hybrid expectation passes; 4 calls, about 199.6 seconds remote.
- Pack 2: 4/4 hybrid expectation passes; 2 calls, about 106.8 seconds remote.
- Pack 4: 4/4 hybrid expectation passes; 1 call, about 59.5 seconds remote.
- Pack 8: 7/8 hybrid expectation passes; 1 call, about 72.6 seconds remote.

The pack-8 result is a real quality miss at this sample size. Pack sizes 1/2/4
are encouraging but only four questions each, so they are not certified
quality gates. Local verification added roughly 1.9 seconds for pack 4 and
3.5 seconds for pack 8. The aggregate-only retained summary contains no
answer text, source IDs, or private titles.

## Decision

Keep packing opt-in and sequential. Do not promote pack size 8 or claim a
general Top-1 improvement. A larger frozen development/holdout packed suite is
required before choosing a production pack size. True parallel fan-out remains
separately approval-gated and was not attempted.

Evidence: `pq-007-live-packed-summary.json`.
