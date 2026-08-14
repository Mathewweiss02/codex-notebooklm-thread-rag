# TM-009 Result

## Implementation

- Updated `skill/codex-notebooklm-thread-rag/SKILL.md` with explicit broad
  temporal precedence and local CLI command selection.
- Added `references/temporal-memory.md` with fresh-task examples, safety rules,
  and local/semantic separation.
- Added `references/temporal-routing.json` with six cold-start cases and stable
  route invariants.
- Updated `references/operations.md` so the CLI, not low-level semantic search,
  is the primary broad temporal verification surface.

## Verification

- Cold-start routing tests: 3 passed.
- Full repository verification passed: 34 Node tests, 71 Python tests,
  compilation, PowerShell parsing, and all runner/doctor/profile-auth/
  profile-ACL/skill-install/config/scheduler integrations.

## Decision

Accept the temporal skill-routing contract. Exact period membership and
chronological context always begin locally; NotebookLM remains an optional
later candidate/synthesis path whose claims require local verification.

## Limitations

- The cold-start evaluation verifies the installed guidance and route table;
  it does not pretend to be a model-behavior guarantee for every future task.
- The temporal index/bootstrap diagnostic is explicit but not yet automatically
  built by the one-command skill route; that is an operations/real-corpus gate.
- NotebookLM source mapping, remote claim verification, and parallel-query
  topology remain later queued lanes.

## Next move

Advance to `NLM-001`: implement exact thread-to-current-ready-source mapping
without selecting or mutating the persistent CLI-chat notebook.
