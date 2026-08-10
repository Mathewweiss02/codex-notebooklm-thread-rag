# Findings

## Confirmed

- The live deployment currently reconciles 130 visible tasks to 132 unique live sources with no missing or untracked sources.
- The current branch is four commits ahead of main and its existing offline and integration tests pass.
- The doctor can falsely pass a stale runner because it checks only whether `LastSuccessAt` exists.
- NotebookLM auth JSON can report `status=error` while the CLI exits successfully, so exit-code-only health checks are unsound.
- Explicit task scope prevents a newly created eligible task from enrolling automatically.
- Automated disposable search and persistent CLI chat conflict when they share one notebook conversation.
- The fresh 24-case current-corpus benchmark achieved 24/24 semantic candidate recall, 23/24 raw unique-candidate Top-1, and 24/24 hybrid Top-1 after correcting two equivalent-sibling ground-truth labels.
- Query redaction implements fewer credential/path shapes than projection redaction.
- Projection revisions and run/search reports have no retention bound.
- The scheduler's 14-minute execution limit is shorter than the observed initial upload duration of roughly 28 minutes.
- Sync validation rejects missing expected sources but does not reject unrelated extras.
- CI triggers once for push and once for pull request on the same branch update.
- The top-level NotebookLM package is pinned, but the transitive environment is not locked or continuously audited.
- Protected `main` now requires strict `test-windows` status, pull requests, and resolved conversations; force pushes/deletion are disabled and `v0.1.0` is published.

## Suspected bottlenecks

- The largest immediate bottleneck is validation: several important properties work but are not continuously proven.
- The first-fit planner preserves task locality and reserve capacity, but stateless full replanning causes 64.62% shared-assignment churn at 5x and 83.08% at 10x; sticky ownership is the scaling bottleneck.
- The largest UX bottleneck is multiple low-level scripts without a single CLI-first lifecycle command.
- Semantic candidate recall remains the non-negotiable architecture gate; the current 24-case corpus passed it at 100%.
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
