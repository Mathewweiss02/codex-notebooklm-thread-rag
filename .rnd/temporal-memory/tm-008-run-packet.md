# TM-008 Run Packet

## Mission

Expose the resolver, temporal index, and context packer through one clean
fresh-task-friendly local CLI without requiring NotebookLM, MCP, or low-level
script knowledge for exact temporal questions.

## Surface

- `when`: resolve an expression or explicit range.
- `recap`: build the standard local evidence pack.
- `context`: build brief/standard/deep packs with optional thread and segment
  scope.
- `find`: deterministic lexical evidence matching inside a resolved period.
- `compare`: separately resolve two periods and compare canonical event IDs.

## Invariants

- The resolver captures one `now` and emits machine-readable bounds.
- The index remains local authority; errors are not empty results.
- `recap/context` preserve pack coverage, provenance, and omission rules.
- `find` never claims semantic completeness; its lexical contract is explicit.
- `compare` does not concatenate or chronology-mix two periods.
- JSON is the default output; `--human` is a presentation layer over the same
  result. Failures return a nonzero exit and stable `status=error` code.

## Method

1. Build a temporary SQLite index through the existing event handoff.
2. Invoke every command through the actual Python CLI subprocess.
3. Verify shared range fields, evidence coverage, lexical match identity, and
   period-delta counts.
4. Verify backwards/invalid ranges fail machine-readably.
5. Run full repository verification.

## Reproducibility commands

```powershell
$python = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe"
& $python -m unittest tests.test_thread_temporal_cli -v
& $python scripts\thread_temporal_cli.py --human when --expression yesterday --timezone America/New_York
& .\tests\run_all.ps1
```

## Stop condition

Do not promote the CLI if fresh users need to know internal script sequencing,
if a temporal error becomes an empty result, or if a command silently invokes
NotebookLM for exact local selection.
