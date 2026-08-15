# Experiment Result

## Experiment

- ID: `rnd-014`
- Title: Improve acceptance and ranking generalization
- Status: offline policy comparison complete; live diagnostic candidate not promoted

## Scope and integrity

- Inputs were the visible development reports `dev1-v3-hybrid.json`,
  `dev2-v3-hybrid.json`, `dev3-hybrid.json`, and the visible sibling report
  `sibling-v3-hybrid.json`.
- The sealed holdout was not opened, inspected, or used for tuning.
- The comparison replayed the recorded candidate features and preserved the
  existing acceptance/abstention contract. No production constants or runtime
  behavior were changed by this experiment.
- The comparison covered 6 semantic-weight values, 5 local-weight values,
  6 title-weight values, 3 duplicate-group bonuses, and 4 by 3 tie-policy
  combinations: 6,480 frozen ranking policies.

## Evidence

The current policy scored as follows on the visible reports:

| Report | Candidate recall | Hybrid Top-1 | False positives |
| --- | ---: | ---: | ---: |
| dev1 | 31/32 | 31/32 | 0/8 |
| dev2 | 31/32 | 30/32 | 0/8 |
| dev3 | 32/32 | 32/32 | 0/8 |
| sibling | 12/12 | 12/12 | 0/0 |

The strongest zero-false-positive policy that preserved the passing dev3 and
sibling reports used semantic/local/title/duplicate weights of `1.5/1/5/3`
with a strict tie policy. Its replay result was:

| Report | Candidate recall | Hybrid Top-1 | False positives |
| --- | ---: | ---: | ---: |
| dev1 | 31/32 | 31/32 | 0/8 |
| dev2 | 31/32 | 31/32 | 0/8 |
| dev3 | 32/32 | 32/32 | 0/8 |
| sibling | 12/12 | 12/12 | 0/0 |

The improvement is confined to one visible related-decoy ranking error. The
remaining dev1/dev2 candidate-recall misses are absent remote candidates, so
reranking alone cannot repair them.

## Decision

- Do not change the production default from this offline replay.
- Preserve the candidate policy as a named, provenance-recorded live
  diagnostic once the benchmark supports explicit policy selection.
- A live development run must reproduce the result with the same frozen suite,
  zero false positives, no scope violations, and acceptable latency before any
  consideration of promotion. Any final promotion still requires three
  consecutive frozen passes and a newly authored sealed holdout.

## Next move

Add explicit ranking-policy selection to the benchmark surface, then run the
candidate policy only against the visible development suite after the upstream
rate-limit cooldown. Keep the baseline and candidate reports separate; do not
spend the holdout or create replicas for this ranking experiment.
