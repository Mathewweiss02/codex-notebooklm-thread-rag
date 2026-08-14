# TM-006 Run Packet

## Mission

Choose a deterministic activity-segmentation policy for the temporal context
layer without tuning against private corpus text or sharing implementation code
with the expected-result oracle.

## Hypothesis

A thread-local inactivity threshold can produce useful deterministic activity
units if the boundary is explicit, exact-threshold gaps are defined, and the
policy does not split solely at local-date boundaries.

## Variables

- Candidate inactivity thresholds: 15, 30, 60, and 120 minutes.
- Boundary rule: a new segment begins only when the timestamp gap is strictly
  greater than the threshold.
- Domain boundary: thread IDs never merge into one activity.
- Date boundary: midnight alone never splits an activity.

## Oracle and metrics

The fixture contains independent activity labels for 17 synthetic events. It
includes cross-midnight continuity, a 45-minute continuation, an exact
60-minute continuation, a 61-minute split, and 70/75/130-minute splits.
Pairwise precision, recall, F1, false merges, false splits, and exact partition
equality are measured. The harness is independent of the future production
segmenter and uses no private message text.

## Method

1. Generate the frozen labeled fixture in the harness.
2. Sort each thread by UTC timestamp and event ID.
3. Apply each candidate threshold with the strict `gap > threshold` rule.
4. Compare predicted same-activity pairs to oracle same-activity pairs.
5. Select the smallest candidate with zero false merges and zero false splits.
6. Record the result digest and limitations before any context-packer code.

## Stop condition

If no candidate produces an exact oracle partition, do not promote a threshold;
expand the experiment with a documented oracle or choose an explicit
abstention/uncertainty policy.

## Reproducibility command

```powershell
$python = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe"
& $python .rnd\temporal-memory\tm-006-segmentation.py --out .rnd\temporal-memory\tm-006-segmentation-result.json
```
