# Codex NotebookLM Thread RAG Ultra Instinct Program

## Goal

Turn the current working CLI-first Codex-to-NotebookLM retrieval system into an evidence-driven, self-enrolling, recoverable, capacity-aware system whose quality can be measured across every important axis. Preserve NotebookLM as the current semantic backbone while continuously testing whether any architectural seam has a materially better option.

## Desired outcome

- A trustworthy release that fixes every confirmed audit defect.
- A live deployment that enrolls new visible tasks safely and reports when capacity prevents enrollment.
- Persistent human CLI conversations isolated from disposable automated retrieval chats.
- A repeatable 20+ case benchmark and a measured radar scorecard.
- A ranked long-term research queue for freshness, scale, accuracy, resilience, privacy, cost, and operability.

## Non-goals

- Do not expose credentials, private task IDs, raw session files, or NotebookLM IDs in Git.
- Do not delete unrelated NotebookLM sources or local files outside guarded lineage and retention rules.
- Do not replace NotebookLM merely because another architecture is fashionable; alternatives must win measured comparisons.
- Do not pretend an unmeasured axis is maxed out.

## Success signals

- Health checks reject stale runner state and JSON auth failures.
- Every newly visible eligible task is enrolled or produces an explicit capacity/error decision.
- Dedicated retrieval notebooks reject untracked sources and never erase persistent CLI chat history.
- At least 20 varied cases achieve 100% semantic candidate recall and at least 95% hybrid Top-1.
- Retention is bounded, recoverable, dry-run-first, and lineage-aware.
- CI runs once per PR update, dependencies are reproducible, and the release is protected and tagged.
- Every radar axis has a metric, evidence timestamp, confidence level, target, and stop condition.

## Current biggest unknown

Whether the present NotebookLM semantic-candidate plus local deterministic rerank architecture keeps its accuracy, latency, and source-capacity advantages as the corpus and update rate grow by an order of magnitude.

## Phases

- [x] Mission framing
- [x] System mapping
- [x] Broad bottleneck discovery
- [x] Initial experiment design
- [x] Queue prioritization
- [x] Release-critical implementation and validation
- [x] Live 20+ case benchmark
- [x] Live migration and release
- [ ] Wide architecture experiments
- [x] Evidence-backed radar scorecard iteration

## Next planning packet: personal retrieval modes and temporal UX

### Goal

Make everyday use conversational and fast without weakening benchmark independence or authoritative local verification. Determine whether the timestamps already present in every projection are sufficient before adding any timeline source or index.

### Product decision to test

- `chat`: persistent NotebookLM conversation for normal personal knowledge work and follow-up questions. This should be the default human-facing mode.
- `lookup`: independent task discovery with local verification. Conversation reset is explicit or policy-controlled, not silently applied to ordinary chat.
- `benchmark`: mandatory clean conversation before every case and every retry so earlier cases cannot bias later scores.
- `local-time`: local timestamp/event search first for questions such as "what was I doing today?" or "when did I ask for this refactor?"; NotebookLM is used only when cross-task synthesis adds value.

### Phase 1: establish apples-to-apples baselines

- [x] Inspect upstream conversation locks, client concurrency ceilings, and citation-position metadata.
- [x] Build an answer-text-free prompt-packing benchmark harness with per-question citation mapping.
- [ ] Measure pure persistent NotebookLM CLI chat, one-shot disposable lookup, and the complete verified wrapper on the same small query set.
- [ ] Separate conversation-reset, remote answer, retry, reconciliation, and local-verification latency.
- [ ] Record answer usefulness, cited-task recall, context carryover, and contamination risk, not latency alone.
- **Status:** in_progress

### Phase 2: test temporal questions before adding data

- [ ] Build a development-only temporal suite covering today, yesterday, date ranges, exact "when did I..." questions, cross-thread daily summaries, and no-activity periods.
- [ ] Score exact timestamp/event-window accuracy against authoritative local JSONL.
- [x] Smoke-test existing local timestamp/event search without adding duplicate timeline sources; `--today` returned timestamped prior-task evidence.
- [ ] Compare local-first answers with NotebookLM synthesis for broad questions such as "what was I working on today?"
- **Status:** pending

### Phase 3: choose the minimum timeline architecture

- [ ] If existing projections answer temporal questions well, add only routing/UX commands.
- [ ] If they fail cross-thread summaries, test a lightweight date index containing task/date/title/event pointers rather than duplicated message bodies.
- [ ] Reject daily/monthly duplicated transcripts if they increase source count, citation ambiguity, or retrieval bias.
- **Status:** pending

### Phase 4: define conversation and retry controls

- [ ] Design explicit `chat`, `lookup`, and `benchmark` modes with visible conversation behavior.
- [ ] Preserve persistent chat by default for human use; expose `new conversation`/`one shot` as deliberate controls.
- [ ] Keep mandatory resets inside benchmark execution.
- [x] Implement an explicit no-retry `--fast` control without changing balanced benchmark behavior.
- [ ] Compare live no-retry casual lookup, current bounded retry, and user-requested high-confidence retry on the same query set.
- **Status:** pending

### Phase 5: implementation gate

- [x] Implement the evidence-supported low-risk controls: `--today`, `--fast`, marker-first packed citation mapping, and per-section local reranking.
- [ ] Defer production batch routing and notebook replicas until the quality/sample-size gates pass.
- [ ] Preserve the 24-case regression, 12-case sibling, conversation-integrity, privacy, and local-authority gates.
- [ ] Keep acceptance/ranking work (`rnd-014`) separate from temporal UX so improvements remain attributable.
- **Status:** pending

### Success signals

- Ordinary personal chat retains useful follow-up context and is never silently reset.
- Benchmark cases remain independent and reproducible.
- Exact/date-filtered temporal questions return locally verified timestamps, with a target local P50 under two seconds.
- Casual one-attempt NotebookLM use avoids automatic retry latency unless confidence policy or the user requests it.
- No timeline feature duplicates full messages or consumes NotebookLM source capacity without measured benefit.

### Decisions already made

- Do not remove benchmark resets; they are an experimental-control requirement.
- Do not make disposable retrieval the default conversational experience.
- Do not build timeline files until the existing timestamps are tested and shown insufficient.
- "Two attempts" means a second remote NotebookLM ask after an error or fewer than two unique cited tasks; local verification still runs once after candidate collection.

### Planning errors

| Error | Attempt | Resolution |
| --- | ---: | --- |
| Registry role summary returned no rows because it treated each `Configs` entry as a path instead of an object. | 1 | Schema inspection confirmed `Configs` is an object array; read only entry property names, then use its path field without exposing notebook IDs. |
| Generic experiment packet tools selected `rnd-014`/`rnd-013` instead of the explicitly prioritized active `rnd-015`. | 1 | Do not rerun unchanged selection logic; preserve the generated contract shape and patch both artifacts to the user-selected experiment. |
| Batch harness section-parser test expected offsets 10/17, but the literal headings begin at offsets 8/15. | 1 | Keep the parser result and correct the mistaken fixture expectation; rerun the focused suite. |
| First live packed ask exceeded the outer shell's 120-second timeout before the client's 240-second chat timeout. | 1 | Checkpoint inspection showed the detached process completed both size-2 batches and continued; do not rerun. Monitor the existing process, then use a longer wrapper on future runs. |
| Focused tests initially looked for private `sync_config.json` at the repository root. | 1 | Resolve the registered disposable retrieval profile under the private Codex runtime and never assume secrets/config live in the clone. |
| Offline reuse imported the batch harness as a package, but its sibling imports assume script execution. | 1 | Add the repository `scripts` directory to the one-off diagnostic module path; do not repeat the failed import context. |
| One follow-up structural diagnostic had an unmatched parenthesis in inline Python. | 1 | Correct the syntax and rerun only the local read-only diagnostic; no remote request was involved. |
| The complete gate defaulted to system Python 3.11, which lacks the pinned `notebooklm` package, so five suites failed during import. | 1 | Make `tests/run_all.ps1` auto-detect the isolated v0.8.0 runtime while preserving explicit `-PythonPath` for CI and other machines. |
| GitHub push protection rejected the unpublished branch because modified test blobs contained realistic literal fake AWS/GitHub token fixtures, including an earlier local commit. | 1 | Preserve the local branch, squash its intended diff onto a clean branch from `origin/main`, construct synthetic tokens from fragments at test runtime, and push only the clean history; do not bypass protection. |
