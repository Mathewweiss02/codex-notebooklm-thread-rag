# Experiment Run Packet

## Mission

Determine the fastest safe way to answer one or many NotebookLM questions while preserving citation quality, independent benchmark cases, persistent personal chat, and local authority.

## Chosen experiment

- ID: `rnd-015`
- Title: Measure NotebookLM query concurrency and personal latency
- Why now: The user explicitly prioritized batch parallelism and single-query responsiveness. Code inspection proved the transport can overlap RPCs but one notebook conversation cannot safely host independent concurrent asks.

## Hypothesis

Bounded parallel asks across isolated notebook/conversation contexts can materially reduce multi-query wall time. For a single personal query, local-first routing and an explicit no-retry mode can reduce latency more safely than removing verification.

## Variable

- Question packing per remote ask: 1, 2, 4, and 8 questions.
- Independent-worker concurrency: 1, 2, 4, then 8 only after isolation and throttling gates pass.
- Conversation topology: persistent chat, disposable one-shot, and isolated notebook replicas; never race one mutable notebook conversation.
- Retry policy: none, retry on error only, and current retry on error or fewer than two unique citations.
- Routing: local-time/local-exact first versus NotebookLM first.

## Metric or evidence

- Batch wall-clock time, queries per minute, speedup, and parallel efficiency.
- Per-query P50/P95/max latency and first completed answer.
- Semantic candidate recall, Top-1, no-match correctness, citation coverage, and answer completeness per question.
- Conversation cross-talk, persistent-chat conversation/turn invariants, and result-to-question alignment.
- HTTP 429, server, timeout, auth, and parse-error rates.
- Client CPU, memory, network concurrency, local-verification time, and upstream retry counts.

## Method

1. Use development-only questions; do not inspect or reuse holdout-v2 details. Build an initial 16-question mixed set, then expand to at least 50 questions across exact, vague, temporal, related-decoy, duplicate-title, and no-match strata before drawing a production conclusion.
2. Capture the persistent chat conversation ID and turn count before every live round. Never submit experiment questions to that conversation.
3. Establish sequential baselines for pure persistent CLI chat, disposable one-shot lookup, verified lookup without semantic retry, and the current bounded-retry wrapper.
4. Test prompt packing on the disposable retrieval notebook with 1/2/4/8 independently numbered questions in one ask. Require a structured answer and citations for every question; score each question separately.
5. Do not run concurrent asks against one notebook's null/current conversation: upstream serializes them, while separate client processes would bypass only the local lock and create a server race.
6. If prompt packing cannot preserve quality, prepare isolated temporary notebook replicas only after confirming source capacity and explicit user authorization. Run workers at 1, 2, and 4; proceed to 8 only when the previous level has zero cross-talk/auth failures and no material recall loss.
7. After each level, verify persistent chat is unchanged, record account errors and resource usage, and wait for a clean health check before escalating.
8. A 50-question run is a sample-size stage, not the first concurrency stage. Execute it only with the winning safe topology and cap concurrency at the highest level already proven.

## Promotion gates

- Zero conversation cross-talk and zero persistent-chat mutation.
- No auth/session corruption and no repeated throttling.
- At least 100% of baseline semantic candidate recall and no more than one additional Top-1/no-match error in 50 questions.
- At least 1.6x batch speedup at concurrency two or 2.5x at concurrency four; otherwise parallel complexity does not justify promotion.
- Local-first temporal/exact routing P50 under two seconds.
- Casual single-query mode never performs a second semantic ask unless requested or the first attempt errors.

## Stop condition

Stop immediately on conversation contamination, persistent-chat mutation, auth/session corruption, repeated HTTP 429s, three consecutive upstream errors, more than 5% citation-recall loss, or local resource saturation. Cap the first live round at four concurrent isolated workers; eight requires a separate go/no-go review.

## Recommended next lane

- `research-implementation-handoff` if one topology passes every promotion gate.
- `research-synthesis-and-decision` if batching and isolated replicas expose a quality/latency tradeoff.
- Drop same-notebook concurrent chat regardless of throughput because the upstream state model is unsafe for independent questions.
