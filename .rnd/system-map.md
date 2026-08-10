# System Map

## End-to-end flow

1. Codex app-server lists visible archived and active tasks from its state database.
2. The projection layer reads authoritative local JSONL sessions, selects visible user/assistant messages, redacts remote-risk data, and emits revisioned Markdown parts.
3. A bounded explicit scope and source planner decide which complete tasks fit in each retrieval notebook with rolling-update headroom.
4. The sync layer uploads missing revision parts, verifies readiness, checkpoints lineage, and deletes only verified prior revisions.
5. The scheduler repeats projection and sync, records runner state and reports, and periodically reconciles local lineage with live sources.
6. Automated retrieval asks a dedicated NotebookLM retrieval notebook for cited semantic candidates.
7. Local deterministic search reranks only those candidates against authoritative Codex history.
8. The CLI remains the primary human NotebookLM interface; persistent conversational notebooks are separate from disposable retrieval notebooks.
9. Benchmarks, doctor checks, retention, CI, and release controls determine whether a change is safe to deploy.

## Layers and seams

| Layer | Inputs | Outputs | Critical seam |
| --- | --- | --- | --- |
| Codex discovery | App-server state DB | Visible task metadata and session paths | Completeness and stable task identity |
| Session parsing | Local JSONL | Visible messages and parse statistics | Oversized/image-heavy records and schema drift |
| Projection | Messages and task metadata | Sanitized revisioned Markdown | Fidelity, privacy, split quality, source title identity |
| Scope/capacity | Visible tasks, current state, account limit | Explicit enrolled scope and shard plan | Automatic enrollment without silent overflow |
| NotebookLM sync | Projection state and live sources | Ready source lineage | Capacity, interrupted uploads, source integrity |
| Conversation state | Retrieval query and notebook chat | Cited semantic candidates | Disposable automation versus persistent CLI chat |
| Local authority | Candidate IDs and local sessions | Hybrid ranking | Candidate recall ceiling and local rerank precision |
| Operations | Scheduler, auth profiles, reports | Fresh synchronized corpus | Staleness, auth truth, runtime limits, recovery |
| Evidence | Cases, reports, metrics | Release decision and scorecard | Benchmark representativeness and reproducibility |
| Release/supply chain | Source, lock, CI, GitHub policy | Versioned deployable package | Dependency drift, duplicate CI, branch safety |

## Feedback loops

- Retrieval failures become benchmark cases, then drive projection, prompt, rerank, or architecture experiments.
- Capacity pressure changes shard plans before enrollment; it must never silently truncate task coverage.
- Runner age, deferred-active counts, and upload duration tune freshness without guessing.
- Source reconciliation and retention operate from lineage; neither is allowed to infer ownership from title alone.
- Upstream NotebookLM changes are adopted only after compatibility tests and a rollback path.

## Architectural branches worth testing

- Current ace: NotebookLM semantic candidate generation plus local authoritative rerank.
- Multiple dedicated retrieval notebooks with a fan-out/fan-in broker when one source limit is reached.
- A local lexical/vector index as a first-stage router, with NotebookLM used only for ambiguous cases.
- Local-only retrieval for sensitive queries, with NotebookLM used for already-redacted semantic discovery.
- Event-driven projection after task quiescence versus fixed-interval polling.
- Content-addressed source manifests versus title-and-lineage identity.
