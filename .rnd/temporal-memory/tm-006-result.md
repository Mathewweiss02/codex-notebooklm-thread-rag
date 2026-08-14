# TM-006 Result

## What was run

- Executed the independent `tm-006-segmentation.py` harness with pinned
  NotebookLM runtime Python 3.12.4.
- Compared 15, 30, 60, and 120-minute inactivity thresholds.
- Used 17 synthetic events with independent labels for 8 expected activities.
- Repeated the frozen run three times and compared the complete result digest.

## Evidence summary

| Threshold | Pairwise precision | Pairwise recall | F1 | False merges | False splits | Predicted segments | Exact partition |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 15 min | 1.000000 | 0.636364 | 0.777778 | 0 | 4 | 11 | no |
| 30 min | 1.000000 | 0.727273 | 0.842105 | 0 | 3 | 10 | no |
| 60 min | 1.000000 | 1.000000 | 1.000000 | 0 | 0 | 8 | yes |
| 120 min | 0.407407 | 1.000000 | 0.578947 | 16 | 0 | 5 | no |

The result digest was
`b4f57673f7c577b70de5f11ad2f6cac658bb54ec2bc1cbd357efe9c8e6606398` on all
three runs.

## Decision

Accept `activity-segmentation-v1`: thread-local ordering and a new segment when
the gap is strictly greater than 60 minutes. Exact 60-minute gaps remain in
the same segment; local midnight does not split a segment. The durable policy
is in `segmentation-policy-v1.json` and ADR-003.

## Limitations

- The labels are a synthetic decision fixture, not a production-corpus truth
  set. This selects a transparent starting policy; it does not prove that 60
  minutes is universally optimal.
- Topic changes inside an uninterrupted session are intentionally left to
  context packing or later, separately measured subsegmentation.
- Real-corpus parity, long-thread scale, and interruption/recovery behavior
  remain later release gates.

## Next move

Advance to TM-007: implement a hierarchical, budget-aware context packer that
preserves complete selection counts, segment provenance, explicit omissions, and
drill-down expansion.
