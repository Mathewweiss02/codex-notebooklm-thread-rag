# Ultra Instinct Readiness Scorecard

Snapshot: 2026-08-10 (`codex/recursive-eval-loop`, pre-release)

Every score below has an explicit numerator/denominator or normalization rule. Unmeasured properties are excluded instead of receiving guessed values.

| Axis | Evidence contract | Score |
| --- | --- | ---: |
| Frozen regression Top-1 | 24 correct hybrid Top-1 results / 24 regression cases | 100 |
| Visible development Top-1 | Latest frozen bounded-retry result: 32 / 32 positive cases | 100 |
| Visible development candidate recall | Latest frozen bounded-retry result: 32 / 32 positive cases | 100 |
| Latest sealed holdout Top-1 | Holdout-v2: 30 correct hybrid Top-1 results / 32 positive cases | 93.8 |
| Latest sealed holdout candidate recall | Holdout-v2: 32 cases containing a valid expected candidate / 32 positive cases | 100 |
| Latest sealed negative abstention | Holdout-v2: 7 correct abstentions / 8 no-match cases | 87.5 |
| Duplicate-title sibling Top-1 | 12 correct group-aware results / 12 visible sibling cases | 100 |
| Corpus coverage | 130 enrolled visible tasks / 130 visible tasks | 100 |
| Conversation safety | Conversation ID, turn count, and complete Q&A unchanged / 3 invariants | 100 |
| Current health gates | 26 passing live doctor checks / 26 checks | 100 |
| Automated tests | 21 Node + 53 Python passing / 74 tests | 100 |
| Dependency audit | Locked hash-strict audit with zero known vulnerabilities / required release gate | 100 |
| Release controls | Strict CI, PR requirement, conversation resolution, no force push, no deletion, published release / 6 controls | 100 |
| Freshness target attainment | 15-minute near-term quiet target / current 60-minute quiet gate | 25 |
| 10x scale readiness | Largest multiplier within <=10% churn and <=3 fan-out budgets (2x) / 10x target | 20 |

## Not scored yet

- Multi-device ownership and failover
- Content-digest verification of uploaded bytes
- Rate-limit and cost envelope
- Long-running reliability SLO
- Churn/reliability at 15-minute and 5-minute quiet gates
- Selective-router candidate recall across multiple notebooks

## Interpretation

The old regression surface and latest visible development run are perfect, and holdout-v2 proves semantic candidate discovery can reach 100%. The system is still not release-grade because holdout-v2 hybrid Top-1 is 93.8% and negative abstention is 87.5%, both below their governing thresholds. Acceptance/ranking generalization is the next active quality axis; retry latency, freshness, and sticky shard ownership remain parked efficiency/scale axes.
