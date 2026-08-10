# Queue

## Current next item

- ID: `rnd-007`
- Title: Compare local router plus NotebookLM fan-out
- Status: `queued`
- Next lane: `research`
- Reason: Selected because it is actionable now with score 33.5 and strong leverage/uncertainty reduction.

## Queue table

| Rank | Status | ID | Title | Type | Branch | Next lane | Score | Depends on | Blocked by |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | done | rnd-006 | Simulate 2x, 5x, and 10x corpus capacity | experiment | scale-architecture | research | 39.5 | rnd-003 | - |
| 2 | done | rnd-001 | Patch release-critical correctness and safety gaps | implementation | release-safety | implementation | 38.5 | - | - |
| 3 | done | rnd-002 | Run the 20+ case full-corpus semantic and hybrid benchmark | measurement | retrieval-quality | validation | 38.0 | rnd-001 | - |
| 4 | done | rnd-005 | Create the evidence-backed radar scorecard | synthesis | observability | validation | 37.5 | rnd-002 | - |
| 5 | done | rnd-003 | Build capacity-aware automatic task enrollment | implementation | coverage-capacity | implementation | 35.5 | rnd-001 | - |
| 6 | queued | rnd-007 | Compare local router plus NotebookLM fan-out | comparison | scale-architecture | research | 33.5 | rnd-002, rnd-006 | - |
| 7 | queued | rnd-004 | Measure and optimize freshness profiles | experiment | freshness-throughput | research | 33.0 | rnd-001 | - |
| 8 | done | rnd-009 | Harden dependency reproducibility and vulnerability checks | implementation | supply-chain | implementation | 32.0 | rnd-001 | - |
| 9 | queued | rnd-008 | Add content-addressed live source integrity evidence | discovery | source-integrity | research | 28.5 | rnd-001 | - |
| 10 | queued | rnd-010 | Replace arbitrary oversized-line limits with bounded parsing | experiment | parser-resilience | research | 28.5 | rnd-001 | - |
| 11 | queued | rnd-012 | Prove multi-device ownership and failover | experiment | multi-device | research | 24.0 | rnd-003, rnd-008 | - |
| 12 | queued | rnd-011 | Optimize auth refresh cadence | experiment | auth-reliability | research | 22.5 | rnd-001 | - |
