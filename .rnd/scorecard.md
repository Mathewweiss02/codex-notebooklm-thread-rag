# Ultra Instinct Readiness Scorecard

Snapshot: 2026-08-10 (`v0.1.0`)

Every score below has an explicit numerator/denominator or normalization rule. Unmeasured properties are excluded instead of receiving guessed values.

| Axis | Evidence contract | Score |
| --- | --- | ---: |
| Retrieval Top-1 | 24 correct hybrid Top-1 results / 24 cases | 100 |
| Semantic candidate recall | 24 cases containing a valid expected candidate / 24 cases | 100 |
| Corpus coverage | 130 enrolled visible tasks / 130 visible tasks | 100 |
| Conversation safety | Conversation ID, turn count, and complete Q&A unchanged / 3 invariants | 100 |
| Current health gates | 25 passing live doctor checks / 25 checks | 100 |
| Automated tests | 21 Node + 26 Python passing / 47 tests | 100 |
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

The current single-notebook system is release-grade for the measured corpus. The shortest path to a materially larger radar polygon is freshness experimentation plus sticky shard ownership and recall-gated routing; adding more retrieval heuristics is not the current bottleneck.
