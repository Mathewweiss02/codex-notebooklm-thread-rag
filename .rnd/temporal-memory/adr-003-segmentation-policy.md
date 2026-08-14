# ADR-003: Thread-local activity segmentation

## Status

Accepted for the first implementation revision by TM-006 synthetic policy
selection. The policy remains a versioned decision: a future real-corpus
calibration may create `activity-segmentation-v2` and must rerun dependent
context, benchmark, and release evidence.

## Context

The temporal index gives an exhaustive ordered message set, but a useful recap
needs stable activity units. A fixed local-day split loses work that crosses
midnight. A very small inactivity threshold fragments a single work session,
while a large threshold merges separate sessions. The boundary must be
deterministic, inspectable, and independent of semantic ranking.

## Decision

Use `activity-segmentation-v1` with these rules:

1. Select the complete canonical message window before segmentation.
2. Partition by `threadId`; events from different threads never share a segment.
3. Within each thread, sort by `(timestampUtc, eventId)`.
4. Start a new segment only when the gap from the previous event is **strictly
   greater than 60 minutes**. A gap of exactly 60 minutes remains in the same
   segment.
5. Do not split a segment merely because the local calendar date changes.
6. Quarantined, invalid-timestamp, hidden, and empty events are not segment
   members; their counts remain visible in coverage/diagnostic metadata.
7. Every segment retains its event IDs, first/last timestamps, thread ID, and
   source lineage so a summary can be expanded without re-ranking the period.

## Evidence

TM-006 compared 15, 30, 60, and 120-minute thresholds against an independent
17-event, 8-activity oracle. The 60-minute policy was the only candidate with
zero false merges and zero false splits: pairwise precision 1.0, recall 1.0,
F1 1.0, and an exact 8-segment partition. The fixture covered cross-midnight
continuity, a 45-minute continuation, an exact 60-minute continuation, a
61-minute split, and 70/75/130-minute gaps.

## Consequences

- Context packing can use period → local day → activity segment → message
  evidence without duplicating day/week source corpora.
- A single activity may appear under more than one local date; the packer must
  represent that explicitly rather than clone the messages.
- The threshold is a measured starting policy, not a claim that all human work
  follows a 60-minute rhythm.
- Real-corpus calibration and a sealed holdout remain release gates.

## Rejected alternatives

- **15/30 minutes:** fragmented oracle activities with 45- and 60-minute gaps.
- **120 minutes:** merged distinct activities separated by 70/75-minute gaps.
- **Split at midnight:** violates message-level continuity and creates false
  activity boundaries.
- **Semantic clustering as the boundary:** not deterministic enough for local
  temporal completeness and would hide omissions behind ranking behavior.
