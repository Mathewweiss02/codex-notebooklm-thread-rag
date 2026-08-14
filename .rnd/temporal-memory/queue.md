# Queue

## Current next item

- ID: `REL-002`
- Title: Complete seven-day or reset fourteen-day soak
- Status: `active`
- Next lane: `validation`
- Reason: Selected because it is actionable now with score 0.0 and strong leverage/uncertainty reduction.

## Queue table

| Rank | Status | ID | Title | Type | Branch | Next lane | Score | Depends on | Blocked by |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | done | NLM-001 | Implement exact thread-to-current-source mapping | implementation |  | implementation | 0.0 | TM-004 | - |
| 2 | done | NLM-002 | Compare local-only and source-scoped temporal synthesis | comparison |  | research-experiment-runner | 0.0 | TM-007, NLM-001 | - |
| 3 | done | NLM-003 | Build local verifier for temporal NotebookLM claims | implementation |  | implementation | 0.0 | NLM-001, NLM-002 | - |
| 4 | done | OPS-001 | Unify doctor, observability, recovery, and operator UX | implementation |  | implementation | 0.0 | TM-008, NLM-003, PQ-005 | - |
| 5 | done | PERF-001 | Profile and optimize current, 2x, 5x, and 10x corpus paths | experiment |  | validation | 0.0 | TM-008, PQ-005 | - |
| 6 | done | PQ-001 | Expand prompt-packing development benchmark | experiment |  | research-experiment-runner | 0.0 | VAL-001 | - |
| 7 | done | PQ-002 | Prove or reject non-destructive explicit conversation pools | discovery |  | research-experiment-runner | 0.0 | VAL-001 | - |
| 8 | done | PQ-003 | Model and dry-run isolated notebook replicas | comparison |  | research | 0.0 | NLM-001, VAL-001 | - |
| 9 | done | PQ-004 | Choose safe query-isolation topology | decision |  | research-synthesis-and-decision | 0.0 | PQ-001, PQ-002, PQ-003 | - |
| 10 | done | PQ-005 | Implement bounded parallel executor | implementation |  | implementation | 0.0 | PQ-004, NLM-003 | - |
| 11 | blocked | PQ-006 | Run live concurrency ramp 1/2/4/8 then gated 16 | experiment |  | research-experiment-runner | 0.0 | PQ-005 | EXPLICIT-ISOLATED-REPLICA-APPROVAL |
| 12 | done | PQ-007 | Run live packed retrieval quality ramp | experiment |  | validation | 0.0 | PQ-005, REL-001 | - |
| 13 | done | REL-001 | Run shadow comparison and one-machine canary | validation |  | validation | 0.0 | PERF-001, RES-001, SEC-001, OPS-001 | - |
| 14 | active | REL-002 | Complete seven-day or reset fourteen-day soak | validation |  | validation | 0.0 | REL-001 | - |
| 15 | queued | REL-003 | Run fresh sealed holdout and final certification audit | validation |  | validation | 0.0 | REL-002 | - |
| 16 | queued | REL-004 | Publish protected release and rehearse rollback | implementation |  | implementation | 0.0 | REL-003 | - |
| 17 | done | RES-001 | Execute failure-injection and recovery campaign | validation |  | validation | 0.0 | TM-008, NLM-003, PQ-005 | - |
| 18 | done | SEC-001 | Complete privacy, ACL, retention, and supply-chain audit | validation |  | validation | 0.0 | TM-008, PQ-005 | - |
| 19 | done | TM-000 | Freeze current baseline and private temporal oracle fixtures | measurement |  | research-experiment-runner | 0.0 | - | - |
| 20 | done | TM-001 | Approve event, time-range, context-pack, and verification contracts | decision |  | planning | 0.0 | TM-000 | - |
| 21 | done | TM-002 | Run ADR spikes for index engine and indexed-content boundary | comparison |  | research-experiment-runner | 0.0 | TM-000 | - |
| 22 | done | TM-003 | Build canonical event extractor and independent slow oracle | implementation |  | implementation | 0.0 | TM-001, TM-002 | - |
| 23 | done | TM-004 | Build crash-safe incremental temporal index | implementation |  | implementation | 0.0 | TM-003 | - |
| 24 | done | TM-005 | Implement DST-safe temporal expression resolver | implementation |  | implementation | 0.0 | TM-001 | - |
| 25 | done | TM-006 | Measure and choose deterministic activity segmentation | experiment |  | research-experiment-runner | 0.0 | TM-003, TM-004 | - |
| 26 | done | TM-007 | Build hierarchical budget-aware context packer | implementation |  | implementation | 0.0 | TM-004, TM-005, TM-006 | - |
| 27 | done | TM-008 | Create unified local temporal CLI | implementation |  | implementation | 0.0 | TM-007 | - |
| 28 | done | TM-009 | Add fresh-task skill routing and cold-start evaluations | implementation |  | implementation | 0.0 | TM-008 | - |
| 29 | done | VAL-001 | Materialize exhaustive temporal development/validation/holdout suites | measurement |  | validation | 0.0 | TM-003, TM-005 | - |
