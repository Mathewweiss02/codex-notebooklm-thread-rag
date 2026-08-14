# TM-008 Result

## Implementation

- Added `thread_temporal_cli.py` as the unified local temporal command surface.
- Composed the existing Node temporal resolver with the Python SQLite index and
  evidence-only context packer.
- Added `when`, `recap`, `context`, `find`, and `compare` commands with JSON as
  the default and an optional human summary.
- Added explicit command/error/provenance contract in `cli-contract-v1.json`.
- Updated README examples and corrected the live-inventory wording so the old
  130-task/132-source paragraph is clearly historical.

## Verification

- CLI focused tests: 2 passed.
- Actual subprocess coverage exercised `when`, `recap`, `find`, `compare`, and
  invalid explicit ranges.
- Full repository verification passed: 34 Node tests, 70 Python tests,
  compilation, PowerShell parsing, and runner/doctor/profile-auth/profile-ACL/
  skill-install/config/scheduler integrations.
- Manual human output was verified for `when yesterday`.

## Decision

Accept `temporal-cli-v1` as the primary exact-time entrypoint. Keep semantic
NotebookLM search separate: it may find candidate tasks or synthesize a
source-scoped evidence pack later, but it cannot replace local exhaustive
period selection.

## Limitations

- `find` is deliberately lexical and local; semantic topic recovery remains the
  existing NotebookLM/local-rerank path and still needs the later source-mapping
  verifier.
- The CLI assumes the caller has already built the temporal SQLite index; TM-009
  must add fresh-task skill routing and an actionable index/bootstrap diagnostic.
- Real-corpus extractor-to-index replay and local performance floors remain
  release gates.

## Next move

Advance to TM-009: update the installed skill with cold-start routing rules,
examples, diagnostics, and evaluations that prevent broad date questions from
falling through to semantic-only search.
