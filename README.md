# Codex NotebookLM Thread RAG

A Windows-first, incremental semantic-search layer for Codex task history. It projects only visible user/assistant messages, applies one shared remote-redaction contract, uploads revisioned sources to dedicated NotebookLM notebooks, and keeps deterministic local ThreadOps search as the authority and fallback. The `notebooklm` CLI is the primary human interface; Python is internal orchestration and MCP is optional.

## Upstream backbone

This project is a focused synchronization and retrieval layer built on [teng-lin/notebooklm-py](https://github.com/teng-lin/notebooklm-py), not an independent NotebookLM client. The `notebooklm` CLI is the primary operator interface for profiles, authentication, notebooks, sources, diagnostics, and everyday NotebookLM work. The pinned `notebooklm-py` v0.8.0 runtime provides:

- the Python `NotebookLMClient` used by sync, reconciliation, and retrieval;
- the `notebooklm` CLI used for profiles, authentication, limits, and diagnostics;
- the optional `notebooklm-mcp` server as a secondary integration surface, not the main interface; and
- durable master-token recovery for unattended refreshes.

The upstream project uses undocumented Google interfaces and is the compatibility boundary for this repository. This wrapper adds Codex-thread projection, privacy gates, revision-safe synchronization, local verification, scheduling, and the `codex-notebooklm-thread-rag` skill. The wrapper's internal sync scripts use the Python client where they need source-ID lineage and guarded revision swaps; users and agents should prefer the CLI for normal operation. See [docs/UPSTREAM.md](docs/UPSTREAM.md) for the complete responsibility and upgrade map.

This project does **not** repair broken Codex tasks or replace Codex storage. It helps rediscover relevant tasks and facts, then requires local verification before acting.

## Deployment and evidence baseline

The v4 ADS-PC evaluation used 20 varied real tasks, including renamed tasks, forks, active/archive pairs, giant histories, unrelated titles, split sources, and close decoys:

- 28,056 visible messages projected into 32 ready sources (17.18 MB).
- Zero surviving credential patterns, raw user-home paths, reasoning records, or tool payloads in the inspected projection.
- Raw NotebookLM citation-order Top-1: 18/20 (90%); candidate recall: 20/20 (100%).
- End-to-end hybrid Top-1 after authoritative local reranking: **20/20 (100%)**.
- 32/32 live source reconciliation with no missing sources, title drift, or duplicate titles.
- Both isolated auth profiles passed exact-account checks, passive live checks, browserless master-token renewal, and restricted-ACL tests.
- The installed global skill completed a scheduled v4 refresh with exit code 0; all 20 unchanged tasks were skipped without duplicate uploads.

The current ADS-PC deployment is newer and larger than that pilot: the latest scheduled projection observes 145 visible tasks and 147 current source parts, with no source-map problems in the latest live reconciliation. The earlier 130-task/132-source and 312-task/338-part results are historical baselines, not today's deployment size.

The historical 130-task corpus passed a fresh saved 24-case evaluation on 2026-08-10: semantic candidate recall was 24/24 (100%), raw unique-candidate Top-1 was 23/24 (95.83%), and fused semantic/title/local Top-1 was 24/24 (100%). That suite is now classified as a frozen regression baseline, not proof of generalization; the initial 2026-08-14 live inventory observed 140 visible tasks and the latest scheduled projection observes 145.

A broader governed evaluation added 40 visible development cases, 40 sealed holdout cases, negative/no-match queries, uncertainty intervals, immutable evidence, and a 12-case duplicate-title sibling slice. The first sealed holdout scored 30/32 semantic candidate recall, 24/32 hybrid Top-1, and 8/8 correct abstentions. Those honest results block a release-grade retrieval claim and motivate bounded semantic retry. The spent holdout is diagnostic only; a fresh sealed holdout and three consecutive frozen runs are required for promotion.

An opt-in local-first/source-scoped development canary reached 32/32 semantic candidate recall, 32/32 hybrid Top-1, and 0/8 false positives in one pass. Follow-up adaptive-retry evidence exposed a 1/8 negative false-positive path after an empty initial response; a broad quorum fix over-abstained on legitimate one-thread positives, and later live attempts hit NotebookLM rate limiting. The route is therefore not promoted or release-certified; three consecutive frozen passes and a fresh unspent holdout remain required.

The first fresh sealed holdout for that policy did not pass: semantic candidate recall was 32/32 (100%), but hybrid Top-1 was 30/32 (93.75%) and false-positive rate was 1/8 (12.5%). The holdout is preserved as immutable aggregate evidence and is not used for case-level tuning. This means the current bottleneck is acceptance/ranking generalization—especially negative rejection—not semantic candidate discovery. A new development-only rejection experiment and another independently authored sealed holdout are required before release claims.

These are machine-specific results. NotebookLM is the candidate finder; local Codex history remains the authority.

## Architecture

```text
Codex session JSONL
        |
        v
sanitized incremental projection + capacity transaction
        |  quiet gate / rolling source reserve
        +------------------------------+
        v                              v
dedicated retrieval notebook          persistent CLI chat notebook
(disposable automation chat)          (conversation is never reset by search)
        |
        v
cited semantic candidate task IDs
(bounded fresh retry on error/singleton)
        |
        v
candidate-only local reranking
        |
        v
local Codex evidence verification
        |
        +--> deterministic ThreadOps search fallback
```

The scheduler polls every 15 minutes. Unchanged tasks are skipped. A changed task normally waits until it has been quiet for 60 minutes; a previously projected task still changing for six hours becomes eligible at the hard ceiling. With the default profile, “live” therefore means eventually available after quiescence, not real-time. Shorter 15- and 5-minute profiles are research experiments and must earn promotion through measured churn, reliability, and retrieval results.

## Requirements

- Windows PowerShell 5.1 or newer.
- Node.js.
- Python 3.12.
- [`uv`](https://docs.astral.sh/uv/).
- Codex Desktop with local session history.
- A Google account with NotebookLM access.

There is no NotebookLM API key, public OAuth scope, or service-account path. Authentication is a credential-bearing Google browser session or a durable master token managed by `notebooklm-py`. Never paste those values into a command, issue, log, or chat.

## 1. Install

```powershell
.\install.ps1
```

This creates an isolated runtime at `%USERPROFILE%\.codex\runtimes\notebooklm-py-0.8.0`, synchronizes the complete hash-bearing `uv.lock` graph, installs the upstream Python API, CLI, headless-auth support, and MCP server, runs the complete offline test suite, and installs the global `codex-notebooklm-thread-rag` skill under `%USERPROFILE%\.codex\skills`. It does not modify another `notebooklm` installation. Upgrades preserve a rollback copy under `%USERPROFILE%\.codex\skill-backups`.

Verify the installed upstream surfaces:

```powershell
$Runtime = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts"
& "$Runtime\notebooklm.exe" --version
& "$Runtime\notebooklm-mcp.exe" --help
```

Use `notebooklm.exe` for normal work. Treat `notebooklm-mcp.exe` as an optional adapter for an MCP host, not as the default way to operate the system.

## 2. Authenticate

Normal browser auth:

```powershell
.\scripts\notebooklm_profiles.ps1 login-personal -Account "you@example.com"
```

Durable unattended auth:

```powershell
.\scripts\notebooklm_profiles.ps1 master-login-personal -Account "you@example.com"
```

The wrapper defaults to upstream's isolated `chromium` login. Pass `-Browser chrome` or `-Browser msedge` only when the default browser cannot complete the account's sign-in policy. Keep the temporary sign-in window open until the command reports success.

For a second account, use `work` instead of `personal`. Leave the sign-in window open until the terminal reports success. Verify browserless renewal:

```powershell
.\scripts\notebooklm_profiles.ps1 refresh-personal
.\scripts\notebooklm_profiles.ps1 doctor-personal
```

The account email selects the intended Google identity; it is not a token. Never pass or save the `--oauth-token` value unless you understand its exposure risk.

Scheduled upkeep uses the upstream CLI command `auth refresh --verify`. A personal profile with a master token can fully re-mint an expired session. A Workspace profile that blocks master-token exchange can still rotate and verify its existing browser session, but may eventually require interactive login when an administrator-enforced session expires.

The thread-RAG wrapper intentionally uses profile names `personal` and `work`. If an older upstream installation uses `main` and `alt`, verify the account mapping first and rename the profiles without copying credential files. Use the pinned executable explicitly; a different `notebooklm` found earlier on `PATH` can be an older installation:

```powershell
$NotebookLm = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\notebooklm.exe"
& $NotebookLm profile list --json
& $NotebookLm profile rename main personal
& $NotebookLm profile rename alt work
```

Only rename after confirming which email each profile represents. Durable automation additionally requires `master_token.json`; a profile with only `storage_state.json` still needs the one-time `master-login-*` flow.

## 3. Lock down credentials

Profiles live under `%USERPROFILE%\.notebooklm\profiles`. Master tokens are durable Google credentials. Restrict the selected profile directory to the Windows user and `SYSTEM`, and never commit or sync it. See [SECURITY.md](SECURITY.md).

## 4. Create isolated retrieval and CLI chat notebooks

Create notebooks through the NotebookLM CLI. Use a dedicated `retrieval` notebook for automated semantic searches; its conversation is intentionally disposable. If you want ongoing human CLI conversations over the same corpus, create a second `chat` notebook and a second config/projection root. Automated search ignores `chat` configs and can never reset their conversation history.

Start with a bounded retrieval config:

```powershell
.\New-SyncConfig.ps1 -Device "my-pc-retrieval" -NotebookId "RETRIEVAL_NOTEBOOK_ID" -Profile personal -NotebookRole retrieval -ThreadIds @(
  "THREAD_ID_1",
  "THREAD_ID_2"
)
```

For persistent CLI chat over the same task corpus, create the second config with the same initial IDs:

```powershell
.\New-SyncConfig.ps1 -Device "my-pc-chat" -NotebookId "CHAT_NOTEBOOK_ID" -Profile personal -NotebookRole chat -ThreadIds @(
  "THREAD_ID_1",
  "THREAD_ID_2"
)
```

Each config has independent projection/source lineage. Empty task scope is rejected. `-AllowAllThreads` remains an explicit high-risk opt-in. The default safer path is `AutoEnroll=true`: every normal runner pass inventories visible tasks, stage-projects unknown tasks, reads the live NotebookLM limit, proves immediate and rolling-update headroom, and atomically extends the explicit allowlist. It refuses the whole enrollment when any task or capacity gate is unresolved.

## 5. Dry-run, upload, and reconcile

```powershell
$Config = "$env:USERPROFILE\.codex\thread-rag\my-pc-retrieval\sync_config.json"
.\scripts\notebooklm_thread_sync_runner.ps1 -Config $Config -DryRun
.\scripts\notebooklm_thread_sync_runner.ps1 -Config $Config
.\scripts\notebooklm_thread_sync_runner.ps1 -Config $Config -ReconcileOnly
```

Runner `-DryRun` writes the sanitized local projection, manifest, and state needed for validation, then performs only live read checks against NotebookLM. It does not create, upload, replace, or delete NotebookLM sources.

When the config has `TemporalRefresh=true` (the retrieval profile), the runner also builds a timestamp-preserving temporal handoff and SQLite index from the same projection snapshot. The refresh copies canonical session files into a stable staging area, verifies the extractor output and index before promotion, and preserves the last-good derived state on failure. The `chat` profile leaves this step disabled so persistent CLI conversation state remains separate from automated retrieval.

The sync uploads a new revision fully before deleting only the old source IDs already linked to that task. It refuses schema-policy drift, missing parts, size drift, oversized skipped visible messages, lineage-mismatched deletion, duplicate source identity, and unrelated sources in a dedicated notebook.

Plan or apply enrollment manually when diagnosing capacity:

```powershell
& "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe" .\scripts\notebooklm_thread_enroll.py --config $Config
& "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe" .\scripts\notebooklm_thread_enroll.py --config $Config --apply
```

## 6. Benchmark retrieval

Create a local, gitignored `retrieval_cases.json` with vague remembered queries and expected task IDs. Then run:

```powershell
& "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe" `
  .\scripts\notebooklm_thread_retrieval_benchmark.py `
  --state "$env:USERPROFILE\.codex\thread-rag\my-pc-retrieval\state.json" `
  --cases .\retrieval_cases.json `
  --profile personal `
  --notebook-id NOTEBOOK_ID `
  --confirm-disposable-retrieval-notebook `
  --max-semantic-attempts 2 `
  --transport-max-retries 0 `
  --threshold 0
```

The live benchmark stores hashes, ranks, source IDs, and task IDs—not answer text. It retries from a fresh disposable conversation only when an attempt errors or produces fewer than two unique cited tasks. Raw citation order and per-attempt evidence remain diagnostic. Measure the actual retrieval contract by fusing semantic rank, query-to-title overlap, and candidate-only local evidence:

```powershell
& "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe" `
  .\scripts\thread_rag_hybrid_benchmark.py `
  --raw-report "PATH_TO_RAW_REPORT" `
  --cases .\retrieval_cases.json `
  --state "$env:USERPROFILE\.codex\thread-rag\my-pc-retrieval\state.json" `
  --out "PATH_TO_HYBRID_REPORT" `
  --threshold 0.95
```

Private benchmark suites support `match` and `no_match` expectations, acceptable sibling IDs, development/holdout splits, corpus fingerprints, and separate query/label digests. Use `thread_rag_benchmark_audit.py` to seal a frozen suite, `thread_rag_benchmark_score.py` for holdout-safe scoring, and `thread_rag_benchmark_archive.py` to preserve immutable evidence outside operational retention. Private suites, seals, labels, queries, IDs, and reports are gitignored.

The source-scoped development benchmark is rate-limit circuit-breaker guarded:
after a terminal classified rate-limit case it stops the run and records an
incomplete aggregate instead of continuing to spend requests during cooldown.
Both benchmark entry points set the pinned NotebookLM transport retry budget to
zero by default. `--transport-max-retries` may be raised to at most `3` for a
deliberate transport-retry experiment; this is separate from
`--max-semantic-attempts`, which controls fresh benchmark asks. The selected
transport budget is recorded in the report so latency and rate-limit evidence
cannot include hidden middleware retries.
Holdout aggregate-only scoring is computed from in-memory records before
per-case results are sealed away, so hidden details never erase latency, error,
scope, or completion gates.

Local hybrid ranking is explicitly policy-selectable for reproducible
development experiments. `baseline` remains the default. `generalization-v1`
is the opt-in `rnd-014` candidate retained from offline visible-development
replay; it is not a release promotion and every report records the selected
policy. Compare it only on the visible development suite until a live policy
run, three frozen passes, and a fresh sealed holdout support promotion.

Require 100% semantic candidate recall, at least 97.5% hybrid Top-1, at most 5% false-positive and false-negative rates, and three consecutive frozen runs. Do not tune on holdout case details or relabel hard cases after scoring.

The experimental `notebooklm_thread_batch_benchmark.py` can measure 2/4/8 independently numbered questions in one disposable ask. It maps citations to each answer section, reranks each section locally, and stores no answer text. Do not treat prompt packing as production-ready from a small smoke test, and do not race concurrent null-conversation asks against one notebook: upstream intentionally serializes those asks and separate processes can race the server's mutable current conversation.

For true parallel experiments, use the approval-gated isolated-ramp harness. Its
default is a no-mutation capacity plan; live mode requires both explicit flags,
copies projected files without parent source IDs, validates each replica's
source-title fingerprint, runs bounded waves, and writes hashes/counters rather
than notebook IDs, prompts, or answers:

```powershell
& "PYTHON_PATH" .\scripts\notebooklm_isolated_ramp.py `
  --config "$env:USERPROFILE\.codex\thread-rag\ads-pc-pilot\sync_config.json" `
  --pool-sizes 1 2 4 8 16 32 50 `
  --out "$env:USERPROFILE\.codex\thread-rag\temporal\isolated-ramp-dry-run.json"
```

Start live work at the lowest pool size and retain the evidence before
advancing. Use `--cleanup` only after a successful run when the replicas are no
longer needed.

## 7. Schedule

```powershell
.\scripts\install_notebooklm_thread_sync_task.ps1 `
  -Config "$env:USERPROFILE\.codex\thread-rag\my-pc-retrieval\sync_config.json" `
  -TaskName "Codex NotebookLM Thread Sync - my-pc" `
  -Minutes 15
```

The task runs only while that Windows user has an interactive session. Its top-level action uses the configured runtime's `pythonw.exe`, then creates the PowerShell runner with Windows' `CREATE_NO_WINDOW` flag. This keeps the 15-minute sync invisible without weakening exit-code reporting or overlap tracking; do not replace it with a direct `powershell.exe` action or rely on Task Scheduler's unrelated `Hidden` UI setting. Runs are mutex-protected, have a 120-minute execution limit by default, and perform a nightly read-only strict reconciliation. Install a separate scheduled task for a second `chat` config.

## Retention

Generated data is bounded. The runner plans retention by default and applies it only when `RetentionApply=true`. Current and previous source lineage are always protected; any path outside the configured projection root or explicit `search-runs` directory is rejected. The runner also writes sanitized, append-only aggregate records under `ProjectionRoot\soak-evidence`; retention explicitly guards that directory because the 168-hour resource-aware soak must outlive disposable operational report cleanup.

```powershell
& "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe" .\scripts\thread_rag_retention.py `
  --root "$env:USERPROFILE\.codex\thread-rag\my-pc-retrieval" `
  --search-root "$env:USERPROFILE\.codex\thread-rag\search-runs"
```

Review the report before adding `--apply` or enabling scheduled application.

The resource-aware soak monitor reads the protected evidence surface:

```powershell
& "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe" .\scripts\thread_temporal_release_monitor.py `
  --evidence-root "$env:USERPROFILE\.codex\thread-rag\my-pc-retrieval\soak-evidence" `
  --out ".rnd\temporal-memory\resource-soak-monitor.json" `
  --minimum-hours 168 `
  --max-gap-hours 2 `
  --require-resource
```

The evidence records contain only completion time, status, step labels/timings, and aggregate process-resource values. They do not contain notebook IDs, prompts, messages, or child-process output.

## Search contract

1. Use Codex metadata/title search first.
2. If the synchronized notebook is healthy and fresh, use NotebookLM to identify cited candidate task IDs.
3. Rerank only those candidates against local Codex JSONL. The bundled semantic command does this automatically and refuses to return a usable result when local verification fails.
4. Read and verify local evidence before reporting facts or taking action.
5. If freshness, auth, reconciliation, citations, or identity is uncertain, use deterministic local ThreadOps content search.
6. For original instructions, use provenance-aware origin recovery after task discovery.

For a casual lookup where response time matters more than automatic recovery, pass `--fast`. That mode performs one semantic ask and disables the client's automatic HTTP 429/5xx retries. The balanced default retains up to two semantic attempts and transport retries for reliability.

```powershell
& "PYTHON_PATH" .\scripts\notebooklm_thread_search.py "remembered clues" --fast
```

Exact temporal questions should stay local. Message timestamps are already authoritative, and `--today` expands to the machine's current local calendar-day boundaries:

```powershell
node .\scripts\thread_search.mjs --query "what was I doing" --today
node .\scripts\thread_search.mjs --query "when did I ask for the refactor" --after "2026-08-01" --before "2026-08-11"
```

The new temporal evidence layer is available through one local CLI boundary. It resolves a period once, queries the SQLite-derived temporal index, and emits a provenance-preserving context pack without NotebookLM or conversation state:

```powershell
& "PYTHON_PATH" .\scripts\thread_temporal_cli.py when --expression yesterday --timezone America/New_York
& "PYTHON_PATH" .\scripts\thread_temporal_cli.py recap --db "$env:USERPROFILE\.codex\thread-rag\temporal\temporal.sqlite3" --expression yesterday --timezone America/New_York --mode standard
& "PYTHON_PATH" .\scripts\thread_temporal_cli.py find --db "$env:USERPROFILE\.codex\thread-rag\temporal\temporal.sqlite3" --expression yesterday --timezone America/New_York --query "refactor"
& "PYTHON_PATH" .\scripts\thread_temporal_cli.py compare --db "$env:USERPROFILE\.codex\thread-rag\temporal\temporal.sqlite3" --left yesterday --right today --timezone America/New_York
```

`recap` and `context` are evidence-pack commands: they disclose canonical/included/omitted counts, activity segments, local days, source lineage, and drill-down handles. They do not claim that a compressed pack is a complete narrative. NotebookLM source-scoped synthesis and verification remain separate gated steps.

Use `--project PROJECT_LABEL_OR_HASH` on `recap`, `context`, `find`, or
`compare` when the period should be restricted to one workspace. The filter
uses path-free manifest metadata and fails closed when that metadata is not
available. Context packs may include conservative heuristic signals for intent,
completion, unresolved work, artifacts, and decisions; each signal points back
to included event evidence and is not an independent factual claim.

## Multiple accounts and devices

Keep `work` and `personal` profiles separate. Do not infer source limits from a subscription label; query the live limits for each account because entitlements can change. In the initial test both profiles reported tier 2, 500 notebooks, and 300 sources per notebook.

Use one stable device namespace and preferably one notebook per computer. Cross-device search can query both notebooks, while each machine retains independent provenance and credentials. See [docs/MULTI_DEVICE.md](docs/MULTI_DEVICE.md).

## R&D and current boundary

The current release lane is temporal-memory reliability. The live retrieval profile has been wired to refresh the derived index during normal scheduled runs, with aggregate-only diagnostics, refresh-overlap locking, and post-promotion digest verification. The latest stable live check mapped the current state to 145 threads and 147 current source parts with no source-map problems; the temporal index contains 16,671 events, 145 path-free metadata records, and zero quarantines. The local suite currently passes 48 Node tests and 221 Python tests plus PowerShell, runner, doctor, auth, ACL, installation, config, and scheduler integrations. `tests/run_all.ps1` retains the tested commit and aggregate step timings in `.rnd/temporal-memory/` without private content. New runner reports also retain aggregate working-set, private-memory, handle-count, and processor-time diagnostics for the soak gate, and protected append-only aggregate evidence survives operational report retention. The locked dependency audit reports no known vulnerabilities. REL-001 (freshness wiring and canary) is complete. REL-002 accelerated refresh/recovery/fail-closed evidence is green, while the required wall-clock observation window remains open.

The full certification matrix is 133 cases across time interpretation, index integrity, context packing, NotebookLM verification, prompt packing/parallel topology, performance, security, usability, and operations. The current ledger has 117 retained passes, 8 covered rows, and 8 pending rows; versioned local packets retain 101 focused cases, with current-corpus performance, cross-runtime redaction, and row-aligned packed-query evidence included. A row is not considered certified merely because a nearby unit test passes: each release-blocking row needs a retained executable result. Isolated-replica concurrency remains approval-gated; packed queries are the safe current experiment because they issue one remote ask and do not race the persistent chat notebook.

The historical 2026-08-10 130-task/132-source deployment was synchronized and strictly reconciled. Its frozen 24-case regression remains 100%, while the broader first sealed holdout is 93.75% semantic candidate recall and 75% hybrid Top-1; the latter is the governing generalization signal. The separate CLI-chat notebook has the same corpus, persistent conversation policy, and a live test proving automated retrieval does not alter its conversation ID or turns. The newer 2026-08-14 live inventory observed 140 visible tasks; current source counts belong to the live reconciliation artifacts, not this historical paragraph.

A four-question prompt-packing smoke reached 4/4 per-question candidate recall and 3/4 raw/hybrid Top-1 in about 53 seconds end to end, versus about 285 seconds for four individual cached asks. That is a promising roughly 5.4x throughput result, not a promotion: the sample is tiny and one related-candidate ranking remained wrong. Isolated notebook replicas are the next safe true-parallel topology, but require explicit provisioning approval and their own quality/throttling gate.

Scaling beyond one notebook remains an R&D boundary. A measured 2x/5x/10x simulation preserved complete-task locality and 60-source rolling headroom, but stateless replanning moved 64.62% of shared assignments at 5x and 83.08% at 10x; broadcast search reached six notebooks at 10x. Multi-notebook production therefore requires sticky shard ownership and a recall-gated local router, not repeated full replanning.

The durable `.rnd` workspace maps 20 system factors and the broad experiment queue: accuracy, candidate recall, freshness, coverage, source capacity, conversation integrity, reliability, auth truth, source integrity, parsing, retention, observability, privacy modes, reproducibility, upstream resilience, multi-device behavior, CLI UX, cost, and maintainability. The eventual radar/spider chart is generated only from measured evidence; an unknown metric stays unknown rather than receiving an invented score.
