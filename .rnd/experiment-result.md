# Experiment Result

## Experiment

- ID: `rnd-013`
- Title: Prove benchmark integrity before recursive optimization

## What was run

- Froze the existing 24-case suite as regression-only and added versioned benchmark schemas, materialization, sealing, scoring, Wilson intervals, holdout-safe output, and immutable evidence archival.
- Built a 40-case visible development suite (32 match, 8 no-match), a 40-case sealed holdout with the same class balance, and a separate 12-case duplicate-title sibling suite.
- Ran two independent NotebookLM development passes, one sealed holdout pass, the sibling suite, and the frozen regression suite.
- Tested title/local confidence changes, underscore-aware tokenization, duplicate-title group consensus, full-corpus local candidate discovery, naive 50-candidate fusion, and bounded fresh semantic retry.

## Evidence

- Frozen regression remained 24/24 hybrid Top-1.
- Duplicate-title sibling retrieval improved from 4/12 to 12/12 without lowering the frozen regression suite.
- Visible development stabilized at 31/32 and 30/32 hybrid Top-1 across the two recorded semantic passes, with 0/8 false positives in both.
- Raw NotebookLM candidate recall was 31/32 in each development pass, but the omitted case differed: one transient chat error and one sparse citation miss.
- The first sealed holdout scored 30/32 semantic candidate recall, 24/32 hybrid Top-1, 0/8 false positives, and 2/32 candidate false negatives. Case details remained suppressed.
- Local full-corpus discovery alone scored 30/32 candidate recall. Its misses differed from NotebookLM's, so the union reached 32/32 candidate recall on both recorded development passes.
- Naively reranking all 50 local candidates was falsified: Top-1 fell to 25/32 and 26/32 despite 32/32 union recall.
- A fresh live pass recovered the previously omitted college-choice task at semantic rank 2; existing local authority promoted it to Top-1.
- The first bounded-retry frozen development run achieved 32/32 semantic candidate recall, 32/32 hybrid Top-1, and 8/8 correct abstentions. It used 15 retries across 40 cases with zero API errors.
- The first fresh sealed holdout for that frozen policy achieved 32/32 semantic candidate recall, but only 30/32 hybrid Top-1 and 1/8 correct negative abstentions. Case details remained suppressed and the sealed evidence was archived outside the repository.
- Retry raised remote latency to 65.95 seconds P50, 147.62 seconds P95, and 161.59 seconds maximum, so accuracy passed while efficiency remains an explicit optimization target.
- Protected benchmark evidence now lives outside operational retention; the archive refuses digest mutation or overwrite.
- The complete repository gate passes 21 Node tests, 50 Python tests, compilation, PowerShell parsing, and all integration suites.

## Result

- Strongly supported. The governed suite detected benchmark saturation, a retention flaw, upstream retrieval variance, sibling-label ambiguity, a harmful candidate-fusion design, and a remaining ranking/rejection generalization gap that the old 24-case suite could not expose.
- The retrieval system is improved but not release-gate complete. The first holdout is now spent for aggregate diagnosis, and its 75% Top-1 result prohibits claiming generalization success.

## Next move

- Keep the current bounded retry and group-consensus policy frozen as the baseline; do not tune against holdout-v2 case details.
- Expand development-only negative/rejection cases and compare stricter acceptance policies, preserving the 100% semantic candidate-recall requirement and the existing regression/sibling gates.
- Author and seal a new unspent holdout only after a development policy passes; then require three consecutive frozen runs at 100% semantic candidate recall, at least 97.5% hybrid Top-1, and at most 5% false-positive/false-negative rates before completion.
- Keep full-corpus local discovery as a measured rescue branch; do not merge the rejected 50-candidate flood into production ranking.
