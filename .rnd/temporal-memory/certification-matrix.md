# Temporal Memory Certification Matrix

Every release-blocking row must map to an executable test ID and retained result. “Oracle” means an independent slow enumerator over canonical local events, not the production index itself.

## A. Time interpretation and calendar boundaries

| ID | Scenario | Required invariant | Test level |
| --- | --- | --- | --- |
| TIME-001 | Today | Local midnight to now/end of current local day is resolved explicitly | Unit + E2E |
| TIME-002 | Yesterday | Previous local calendar day, not previous 24 hours | Unit + replay |
| TIME-003 | Past 24 hours | Rolling duration differs correctly from yesterday | Unit |
| TIME-004 | Past 7 days | Rolling seven-day window is explicit | Unit |
| TIME-005 | Last week | Previous configured calendar week, Monday–Sunday by default | Unit + UX |
| TIME-006 | Week to date | Current week start through now | Unit |
| TIME-007 | Explicit date | Entire date in selected time zone | Unit + replay |
| TIME-008 | Explicit timestamp range | Half-open `[start,end)` behavior | Unit |
| TIME-009 | Midnight event | Included in exactly one adjacent day | Property |
| TIME-010 | End-of-day millisecond | No double inclusion or loss | Property |
| TIME-011 | DST spring gap | Nonexistent local time is rejected or deterministically normalized and disclosed | Unit |
| TIME-012 | DST fall overlap | Ambiguous time requires/records offset or deterministic policy | Unit |
| TIME-013 | Leap day | February 29 boundaries are correct | Unit |
| TIME-014 | Month/year boundary | December/January and short-month transitions are correct | Unit |
| TIME-015 | Time-zone override | Same UTC events regroup correctly without changing canonical timestamps | Property |
| TIME-016 | Invalid natural phrase | Fails clearly; no guessed period | Unit + UX |
| TIME-017 | No period specified | Command-specific safe default is visible | UX |
| TIME-018 | Future period | Returns explicit no-activity result, not an error or hallucination | E2E |

## B. Canonical event extraction and index integrity

| ID | Scenario | Required invariant | Test level |
| --- | --- | --- | --- |
| IDX-001 | New session | Every visible message indexed once | Integration |
| IDX-002 | Unchanged rerun | No state/content change | Integration |
| IDX-003 | Appended messages | Only new canonical events added | Integration |
| IDX-004 | Active → archived move | One canonical thread remains; identities stable | Integration |
| IDX-005 | Active/archive duplicate | Preferred canonical copy selected deterministically | Unit + replay |
| IDX-006 | Resumed old thread | New messages appear in current period regardless of thread creation date | Replay |
| IDX-007 | Forked thread | Parent/fork identity preserved; no accidental merge | Integration |
| IDX-008 | Subagent thread | Excluded by default and included only under explicit policy | Integration |
| IDX-009 | Compaction summary | Excluded under existing visibility contract | Regression |
| IDX-010 | Tool/reasoning payload | Never indexed as visible conversation content | Security regression |
| IDX-011 | Duplicate message | Stable digest prevents duplicate identity | Property |
| IDX-012 | Same text, different time | Distinct events remain distinct | Unit |
| IDX-013 | Missing timestamp | Explicit quarantine/error policy; never assigned to a guessed day | Unit |
| IDX-014 | Invalid timestamp | Explicit quarantine/error policy | Fuzz |
| IDX-015 | Malformed JSONL line | Bounded diagnostic; valid prior state retained | Fuzz + integration |
| IDX-016 | Partial final line | Retry after completion; no corruption | Failure injection |
| IDX-017 | Oversized visible line | Existing fail-closed policy retained | Regression |
| IDX-018 | Unicode/emoji/bidi | Text and identity remain deterministic | Fuzz |
| IDX-019 | File locked during scan | Bounded retry/degraded state; no partial commit | Failure injection |
| IDX-020 | Concurrent index writers | Single-writer policy; readers see last committed state | Integration |
| IDX-021 | Process kill during commit | Last good index opens and rebuild succeeds | Crash injection |
| IDX-022 | Database corruption | Detected before use; verified rebuild/restore path | Failure injection |
| IDX-023 | Disk full | No canonical loss; clear error; last good index retained | Failure injection |
| IDX-024 | Schema migration | Upgrade and rollback from every released schema | Migration suite |
| IDX-025 | Redaction contract change | Full rebuild required and version mismatch blocks stale use | Integration |

## C. Period selection, activity segmentation, and context packing

| ID | Scenario | Required invariant | Test level |
| --- | --- | --- | --- |
| CTX-001 | Empty period | Honest empty recap with resolved range | E2E |
| CTX-002 | Single message | One correctly attributed activity unit | E2E |
| CTX-003 | One thread, many messages | Complete chronological membership | Replay |
| CTX-004 | Many threads, one day | Every oracle activity unit represented | Replay |
| CTX-005 | One thread crosses midnight | Each message belongs to correct day; relationship retained | Replay |
| CTX-006 | Multiple sessions in one thread/day | Gap policy creates reproducible segments | Unit + replay |
| CTX-007 | Concurrent threads | Timeline order stable with deterministic ties | Property |
| CTX-008 | Giant thread | Budget honored without hiding omission count | Scale replay |
| CTX-009 | Giant day/week | Hierarchical digest remains navigable and complete at activity level | Scale replay |
| CTX-010 | Brief/standard/deep | Deeper mode is a monotonic expansion of evidence | Property |
| CTX-011 | User intent extraction | Every claim points to user evidence | Factuality suite |
| CTX-012 | Completion extraction | Completed vs planned work is distinguished | Factuality suite |
| CTX-013 | Unresolved item extraction | No completed item mislabeled unresolved or inverse | Factuality suite |
| CTX-014 | Artifact/path extraction | Sanitized and provenance-linked | Security + factuality |
| CTX-015 | Project filter | No cross-project leakage; counts disclose filtering | Integration |
| CTX-016 | Topic within period | Time filter is exhaustive first, then semantic filter | Differential |
| CTX-017 | Compare periods | Period evidence remains separate; no chronology mixing | E2E |
| CTX-018 | Drill-down | Expands exact segment without changing parent identity | E2E |
| CTX-019 | Context budget exhausted | Explicit omissions and expansion handles; no silent truncation | Property |
| CTX-020 | Current thread inclusion | Default policy is explicit and override tested | Integration |

## D. NotebookLM temporal synthesis and verification

| ID | Scenario | Required invariant | Test level |
| --- | --- | --- | --- |
| NLM-001 | All selected threads mapped | Current ready source IDs used | Live + fixture |
| NLM-002 | Missing mapped thread | Explicit degraded/local fallback; no silent omission | Integration |
| NLM-003 | Split thread sources | Every current part included once | Integration |
| NLM-004 | Previous revision present | Previous source never treated as current | Integration |
| NLM-005 | Stale/missing source | Ask blocked before remote synthesis | Live canary |
| NLM-006 | Untracked extra source | Dedicated retrieval reconciliation fails | Regression |
| NLM-007 | Wrong-day remote citation | Local verifier rejects claim | Adversarial live |
| NLM-008 | Wrong-thread remote citation | Local verifier rejects claim | Adversarial fixture |
| NLM-009 | Citation-free claim | Rejected/marked unverified under factual mode | Integration |
| NLM-010 | Remote outage | Deterministic local result remains available | Failure injection |
| NLM-011 | Auth expired | Clear failure; no credential output; local fallback | Live recovery |
| NLM-012 | 429/5xx | Mode-specific bounded retry and visible accounting | Mock + live canary |
| NLM-013 | Timeout | Cancellation and no orphan operation | Failure injection |
| NLM-014 | Persistent chat notebook | Never reset or selected by disposable automation | Regression |
| NLM-015 | Disposable retrieval notebook | Reset only under explicit policy | Regression |
| NLM-016 | No NotebookLM benefit | Router stays local rather than paying remote latency | Routing test |

## E. Prompt packing and parallel querying

| ID | Scenario | Required invariant | Test level |
| --- | --- | --- | --- |
| PAR-001 | One question baseline | Frozen quality/latency baseline | Live benchmark |
| PAR-002 | Pack size 2 | Per-question citations map correctly | Live benchmark |
| PAR-003 | Pack size 4 | No quality gate regression | Live benchmark |
| PAR-004 | Pack size 8 | Run only after lower sizes pass | Gated live benchmark |
| PAR-005 | Missing section | Question fails independently; no citation leakage | Parser test |
| PAR-006 | Reordered headings | Stable question identity survives | Parser fuzz |
| PAR-007 | Citation offset drift | Marker-first mapping remains correct | Regression |
| PAR-008 | Shared null conversation | Must serialize or be rejected | Concurrency test |
| PAR-009 | Distinct explicit conversations | Histories remain isolated | Live experiment |
| PAR-010 | Shared conversation follow-ups | Correctly serialized; no race | Live experiment |
| PAR-011 | Replica notebooks | Identical source fingerprints and independent chat state | Live experiment |
| PAR-012 | Concurrency 2 | Quality/isolation/account gates pass | Live ramp |
| PAR-013 | Concurrency 4 | Quality/isolation/account gates pass | Live ramp |
| PAR-014 | Concurrency 8 | Three consecutive passing runs required | Live ramp |
| PAR-015 | Concurrency 16 | Attempted only after explicit gate | Live ramp |
| PAR-016 | Concurrency 32/50 | Separate value/safety approval; never default | Research gate |
| PAR-017 | One child failure | Other results retain identity; aggregate reports partial failure | Integration |
| PAR-018 | Global cancellation | Every request/process terminates; no orphan state | Failure injection |
| PAR-019 | Rate-limit burst | Adaptive limiter backs off within budget | Mock + canary |
| PAR-020 | Cross-question citation | Detected and rejected | Adversarial benchmark |
| PAR-021 | Conversation mutation | Immediate stop and topology rejection | Live safety gate |
| PAR-022 | Scheduler overlap | Query/sync contention is bounded and observable | Integration + soak |

## F. Performance, scale, and resource behavior

| ID | Scenario | Required invariant | Test level |
| --- | --- | --- | --- |
| PERF-001 | Current corpus cold build | Baseline and target retained | Benchmark |
| PERF-002 | No-change incremental run | P95 floor passes | Benchmark |
| PERF-003 | One-thread append | P95 floor passes | Benchmark |
| PERF-004 | Warm day query | P95 floor passes | Benchmark |
| PERF-005 | Cold day query | P95 floor passes | Benchmark |
| PERF-006 | Week context pack | Budget and latency floor pass | Benchmark |
| PERF-007 | 2× corpus replay | Correctness preserved; slope recorded | Scale benchmark |
| PERF-008 | 5× corpus replay | Correctness preserved; slope recorded | Scale benchmark |
| PERF-009 | 10× corpus replay | Correctness preserved; capacity decision explicit | Scale benchmark |
| PERF-010 | Memory pressure | Bounded memory; no runaway Node/Python process | Profiling |
| PERF-011 | Idle state | No polling CPU/memory leak | Soak |
| PERF-012 | Repeated queries | No cumulative memory/file-handle growth | Soak |

## G. Security, privacy, and retention

| ID | Scenario | Required invariant | Test level |
| --- | --- | --- | --- |
| SEC-001 | Credential patterns | Shared redaction contract applies to indexed/context/remote text | Regression |
| SEC-002 | Private paths | No raw home paths in remote projection or reports | Regression |
| SEC-003 | Database ACL | Intended user and SYSTEM only | Installation test |
| SEC-004 | Logs/reports | No auth values, notebook IDs, private prompts, or answer text where prohibited | Secret scan |
| SEC-005 | Query errors | Sensitive input not echoed unsafely | Fuzz/security |
| SEC-006 | Retention | Index backups/reports bounded; current recovery floor protected | Integration |
| SEC-007 | Rebuild/removal | Derived state removable without canonical-data deletion | Recovery test |
| SEC-008 | Dependency update | Lock, hashes, audit, license/risk review | CI gate |

## H. Usability, operations, and release

| ID | Scenario | Required invariant | Test level |
| --- | --- | --- | --- |
| UX-001 | Fresh Codex task | Installed skill selects correct command/mode | Cold-start eval |
| UX-002 | Nontechnical phrasing | “What did I do yesterday?” works without flags | E2E |
| UX-003 | Ambiguous period | Clarifies or discloses deterministic choice | UX eval |
| UX-004 | Empty result | Helpful, honest response | UX eval |
| UX-005 | Degraded remote | Local answer remains understandable | UX eval |
| UX-006 | Diagnostics | User can see mode, range, coverage, retry, verification | Contract test |
| OPS-001 | Scheduled index update | Invisible, overlap-safe, truthful exit status | Windows integration |
| OPS-002 | Doctor | Detects stale/corrupt index, bad scheduler, auth/source drift | Integration + live |
| OPS-003 | Rebuild | One documented command restores derived state | Recovery rehearsal |
| OPS-004 | Rollback | Prior certified release restored without canonical loss | Release rehearsal |
| OPS-005 | Seven-day soak | No required failures, leaks, drift, or unexplained warnings | Soak |
| OPS-006 | Committed-revision proof | Clean tree, complete gates, CI green, evidence hashes recorded | Release gate |
