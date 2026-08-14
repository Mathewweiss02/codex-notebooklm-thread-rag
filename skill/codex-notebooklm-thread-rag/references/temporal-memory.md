# Temporal memory route

Use this route for any question whose meaning depends on a time period or
chronology. The local temporal CLI is the primary user surface; NotebookLM is
not needed for exact selection and must not be used to guess missing coverage.

## Route table

| User intent | Command | Required behavior |
| --- | --- | --- |
| What was I doing yesterday/last week? | `recap` | Resolve once, select the complete half-open period, disclose coverage and omissions. |
| What exact period does “yesterday” mean? | `when` | Return UTC/local bounds, timezone, and captured-now. |
| Load more/less context or one activity | `context` | Use `brief`, `standard`, or `deep`; use `--segment` for drill-down. |
| When did I mention/refactor X? | `find` | Search local sanitized evidence inside a resolved period; do not claim semantic completeness. |
| What changed between two periods? | `compare` | Resolve each period independently and compare canonical event identities without chronology mixing. |

## Examples

```powershell
$python = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe"
& $python "$Skill\scripts\thread_temporal_cli.py" when --expression yesterday --timezone America/New_York
& $python "$Skill\scripts\thread_temporal_cli.py" recap --db "$env:USERPROFILE\.codex\thread-rag\temporal\temporal.sqlite3" --expression yesterday --timezone America/New_York --mode standard
& $python "$Skill\scripts\thread_temporal_cli.py" context --db "$env:USERPROFILE\.codex\thread-rag\temporal\temporal.sqlite3" --expression "last week" --timezone America/New_York --mode deep
& $python "$Skill\scripts\thread_temporal_cli.py" find --db "$env:USERPROFILE\.codex\thread-rag\temporal\temporal.sqlite3" --expression yesterday --timezone America/New_York --query "refactor"
& $python "$Skill\scripts\thread_temporal_cli.py" compare --db "$env:USERPROFILE\.codex\thread-rag\temporal\temporal.sqlite3" --left yesterday --right today --timezone America/New_York
```

For vague semantic memory without a broad period, use the existing
`notebooklm_thread_search.py` candidate-finding route after its doctor/freshness
checks. It is intentionally not the route for exhaustive date/time questions.

## Safety and fallback

- Exact temporal authority is the local canonical Codex history and its
  derived index. A missing index is an actionable `INDEX_MISSING` diagnostic,
  not an empty period.
- Every pack must disclose canonical, included, and omitted counts, activity
  segments, local days, event provenance, and drill-down handles.
- A compressed pack is evidence, not a generated narrative. Do not accept a
  claim without local event evidence.
- NotebookLM may be added later for source-scoped synthesis after the local
  selection and mapping gates pass. Never reset the persistent CLI-chat
  notebook to answer a temporal question.
