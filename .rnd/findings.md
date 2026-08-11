# Findings

## Confirmed

- The live deployment currently reconciles 130 visible tasks to 132 unique live sources with no missing or untracked sources.
- The current branch contains governed recursive-evaluation tooling and sealed holdout evidence on top of the published operational-hardening release.
- The doctor now rejects stale runner success timestamps and parses NotebookLM auth JSON status instead of trusting exit code zero.
- NotebookLM auth JSON can report `status=error` while the CLI exits successfully; the patched health check now validates both status and exit behavior.
- Capacity-aware enrollment now atomically extends explicit task scope when every new task fits live source headroom, and refuses the entire update otherwise.
- Automated disposable retrieval and persistent CLI chat now use separate notebook roles/configs; live testing proved retrieval does not alter the chat conversation.
- The fresh 24-case current-corpus benchmark achieved 24/24 semantic candidate recall, 23/24 raw unique-candidate Top-1, and 24/24 hybrid Top-1 after correcting two equivalent-sibling ground-truth labels.
- The 24-case benchmark is saturated and has no sealed holdout, negative/no-match cases, uncertainty interval, or repeated frozen-run evidence; it is a strong regression baseline but not yet a top-tier generalization benchmark.
- Query and projection now share one remote-redaction contract with cross-surface regression tests.
- Guarded retention now bounds projection revisions and run/search reports while preserving current and previous lineage.
- The scheduler execution limit is now 120 minutes, above the observed initial upload duration of roughly 28 minutes.
- Strict reconciliation now rejects unrelated extras as well as missing expected sources without automatically deleting them.
- CI now runs once per pull-request update and once for direct pushes to `main`, with immutable action SHAs.
- The transitive environment is locked and continuously audited; the final local audit reported no known vulnerabilities.
- Protected `main` now requires strict `test-windows` status, pull requests, and resolved conversations; force pushes/deletion are disabled and `v0.1.0` is published.
- A 40-case development suite, 40-case sealed holdout, and 12-case sibling suite now expose candidate recall, Top-1, abstention errors, uncertainty, latency, and stratum-level behavior without committing private cases.
- The first sealed holdout scored 93.75% semantic candidate recall, 75% hybrid Top-1, 0% false positives, and 6.25% candidate false negatives; this disproves the earlier inference that 24/24 regression performance implied release-grade generalization.
- Duplicate-title group consensus raised the visible sibling slice from 4/12 to 12/12 while preserving the 24/24 frozen regression baseline.
- NotebookLM and local full-corpus discovery are complementary candidate generators (31/32 and 30/32 separately; 32/32 union on both recorded development runs), but flooding the final reranker with 50 candidates reduced Top-1 and was rejected.
- A bounded fresh NotebookLM retry is justified by observed variance: one development omission was a chat error, another was recovered at semantic rank 2 on a fresh live pass and reranked to Top-1.
- Bounded fresh retry produced the first fully passing 40-case development run: 32/32 candidate recall, 32/32 hybrid Top-1, 0/8 false positives, and zero API errors.
- A fresh sealed holdout for the frozen retry policy achieved 32/32 semantic candidate recall, 30/32 hybrid Top-1, 1/8 false positives, and 0/32 candidate false negatives. This rejects release completion while narrowing the immediate bottleneck to acceptance/ranking generalization.
- The passing retry policy invoked a second attempt on 15/40 cases and increased latency to 65.95s P50 and 147.62s P95; retry eligibility and upstream timeout enforcement are now the leading efficiency bottlenecks.
- Operational retention can delete benchmark seals during long runs; immutable benchmark evidence must remain in a separate protected root.
- Every projected visible message already carries its original ISO timestamp and JSONL source line; thread headers also carry created/updated times, so temporal data collection is not the current gap.
- Local ThreadOps search already supports `--after`/`--before`, chronological event windows, and timestamped evidence, making it the natural authority for exact “when” questions.
- Recorded development/holdout runs attribute roughly 47–52 seconds median to one-attempt remote NotebookLM retrieval versus roughly 0.34–0.43 seconds median for local candidate verification. Bounded two-attempt cases measured roughly 80–89 seconds median total.
- Disposable conversation reset is required for benchmark independence but is not an appropriate default for persistent personal CLI chat; these are separate product modes rather than one global policy.
- The live registry already contains both required surfaces: one `chat` config with `DisposableSearchChat=false` and one `retrieval` config with `DisposableSearchChat=true`; both use automatic enrollment. The next gap is routing/UX, not notebook creation.
- Bulk-query parallelism could reduce wall time dramatically, but its feasibility depends on whether the pinned client supports isolated conversations for concurrent asks against one notebook. Sharing one mutable notebook conversation would create cross-talk and invalidate independent retrieval.
- CPU is unlikely to be the leading parallel-query limit because measured local verification is sub-second and the dominant latency is remote. Upstream request throttling, browser-session transport, and conversation state are the primary unknowns.
- The pinned `notebooklm-py` v0.8.0 client exposes `max_concurrent_rpcs` with a default ceiling of 16, an RPC semaphore, and automatic HTTP 429/server-error retries. Chat asks accept an explicit conversation ID, so bounded parallel transport is supported at the client layer even though same-notebook conversation isolation still requires proof.
- The upstream `ChatAPI` intentionally serializes all asks without an explicit conversation ID by notebook ID because the server appends `conversation_id=null` requests to that notebook's current conversation. It also serializes simultaneous follow-ups sharing one conversation ID. Therefore, naïve `asyncio.gather` against one notebook is queued rather than safely parallel.
- Concurrent asks could run only across distinct explicit conversation IDs or distinct notebook IDs. The current public client surface exposes only the most recent conversation and creates a fresh one by replacing/deleting current state, so safe independent same-notebook conversation provisioning is not yet established.
- The CLI's `--new-conversation` path permanently deletes the current conversation before asking; it cannot provision a reusable parallel conversation pool while preserving history.
- The optional upstream REST server defaults its chat route to four concurrent requests, while the lower-level client has a 16-RPC global ceiling and a 100-connection pool. These are implementation guards, not proof that the Google account safely supports those rates.
- `ChatReference` includes `answer_start_char` and `answer_end_char` offsets in addition to source IDs and citation numbers. A structured multi-question response can therefore map citations back to numbered answer sections and be scored per question rather than only as a global citation union.
- The first live prompt-packing smoke test completed all requested answer headings and improved apparent throughput to 2.39 questions/minute at pack size 2 and 5.04 questions/minute at pack size 4. However, only 1/4 and 2/4 questions respectively mapped to the expected task, with 27 and 13 unmapped citations. This fails the quality gate and may combine true retrieval degradation with incomplete citation-to-section mapping.
- Because the answer text was intentionally not retained, the first smoke report cannot distinguish server-omitted answer offsets from an unsupported inline citation-marker format. Add aggregate offset/marker diagnostics before repeating one bounded pack; do not scale the current prompt to 16 or 50 questions.
- The same four development questions were 4/4 candidate hits and 4/4 raw Top-1 individually, taking 285.09 seconds total. Pack size 4 took 47.63 seconds (about 5.99x wall-time speedup) but scored only 2/4 by section; every packed ask started fresh, ruling out accumulated chat history as the explanation.
- A diagnostic pack-size-4 repeat proved all four expected tasks were present in the global citation union. Before marker-first mapping, 3/4 were assigned to the correct question and 2/4 were Top-1; evidence for Q2 had been structurally assigned under Q1.
- Preferring visible `[N]`/`【N】` citation markers over server answer offsets improved the next four-question observation to 4/4 per-section candidate recall and 3/4 raw Top-1 in 50.49 seconds. Because the answer is stochastic and the sample is four, this is evidence of a parser correction, not an accuracy estimate.
- Candidate-only local reranking added 2.56 seconds across four packed questions but remained 3/4. The unresolved question's correct task was present with stronger local evidence, while the semantic-rank-1 decoy survived the existing near-tie rule and then failed the confidence gate. Keep that tuning in `rnd-014`.
- The best observed four-question packed path was about 53.05 seconds end to end versus 285.09 seconds individually, approximately 5.37x faster, with 4/4 candidate recall but only 3/4 accepted Top-1.
- Local temporal retrieval needs no new NotebookLM timeline source: `--today` found two prior tasks with timestamped evidence in 3.03 seconds, and five warmed date-filtered scans measured 1.543 seconds P50. A persistent index may still be justified if cold/large-active-task latency must be consistently sub-second.
- The interactive remote path now exposes `--fast`, which limits the wrapper to one semantic ask and configures the upstream client for zero 429/5xx retries. Balanced retry remains available explicitly for reliability-sensitive use.

## Suspected bottlenecks

- The largest immediate bottleneck is acceptance/ranking generalization: candidate recall passed holdout-v2, while Top-1 and false-positive gates failed.
- The first-fit planner preserves task locality and reserve capacity, but stateless full replanning causes 64.62% shared-assignment churn at 5x and 83.08% at 10x; sticky ownership is the scaling bottleneck.
- The largest UX bottleneck is multiple low-level scripts without a single CLI-first lifecycle command.
- Semantic candidate recall remains the non-negotiable architecture gate; the current 24-case corpus passed it at 100%.
- Benchmark integrity is now the prerequisite bottleneck for recursive optimization; otherwise score-driven changes could overfit case wording or mutable labels.
- Candidate generation variance remains an efficiency and stability concern, but holdout-v2 shows acceptance/ranking generalization is now the main retrieval-quality bottleneck.
- Candidate-set size is an explicit scaling variable: higher recall can lower final accuracy when normalization and distractor density are not controlled.
- Near-equal hybrid evidence should defer to semantic rank when title evidence is equal; duplicate-title consensus should override a corroborated unique candidate only when group/query coverage is at least 50%.
- The largest freshness risk is fixed quiet-period polling without an evidence-based latency/churn policy.
- The largest long-term maintenance risk is duplicated configuration and redaction behavior across PowerShell, Python, and Node.

## Evidence confidence

- High confidence: code inspection, passing tests, live source reconciliation, scheduler state, and retained file counts.
- Medium confidence: NotebookLM remains the best semantic backbone for this workload; current evidence is successful but not comparative.
- Medium confidence: capacity and assignment behavior at 5x to 10x based on replayed observed distributions; query quality at that scale is still unproven.
- Low confidence: multi-device concurrency, rate-limit behavior, and selective-router recall at multi-notebook scale.

## Open questions

- At what corpus size does a local router plus NotebookLM fan-out beat asking every retrieval notebook?
- What is the shortest quiet period that improves freshness without producing upload churn or poorer retrieval?
- Can upstream expose a source-content digest or stable source text export for end-to-end integrity checks?
- Should persistent CLI chat notebooks consume synchronized task sources directly, or should they reference a separate generated digest?
- What evidence is required before an optional local-only trust mode is worth its complexity?
- Can the existing timestamp-enriched thread projections answer cross-thread “what was I doing today?” questions accurately without a separate timeline index?
- What is the measured latency difference between pure persistent NotebookLM CLI chat, one-shot disposable lookup, and the complete verified wrapper?
- Should everyday skill routing default broad/follow-up questions to persistent chat while reserving disposable retrieval for independent task identification?
- How many concurrent asks can one account sustain before latency, errors, citation quality, or conversation isolation regresses?
- Does safe concurrency require separate notebooks, separate client sessions, separate conversation IDs, or only independent request contexts?
- Can `rnd-014` improve the related-candidate near-tie without regressing the sealed acceptance/negative gates, allowing packed 4/4 candidate recall to become 4/4 accepted Top-1?
