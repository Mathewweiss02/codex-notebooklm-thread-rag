# PQ-003 Run Packet: Isolated replica modeling

## Objective

Model the capacity, freshness, cleanup, and account-footprint implications of
using independent retrieval notebooks as parallel workers. This packet is a
dry run only: it must not create, rename, delete, or populate a live notebook.

## Live inputs

- Pinned personal-account limits: 300 sources per notebook and 500 notebooks.
- Two existing configured surfaces: one persistent chat notebook and one
  retrieval notebook.
- Current retrieval projection: 144 projected tasks and 146 current source
  parts.
- Read-only enrollment planning saw 145 visible tasks, one repairable missing
  projection, 146 live sources, and 147 immediate/steady source units after
  that repair; the plan remained within capacity.
- Conservative model input: 147 source parts per replica.
- Reserve: 60 source parts per replica for rolling updates.

## Model

```powershell
$python = "$env:USERPROFILE\.codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe"
& $python scripts/notebooklm_replica_plan.py `
  --source-parts 147 --source-limit 300 --notebook-limit 500 `
  --reserve 60 --existing-notebooks 2 `
  --current-retrieval-notebooks 1 --pool-sizes 1 2 4 8 `
  --out "$env:USERPROFILE\.codex\thread-rag\temporal\pq-003-replica-plan.json"
```

The planner is arithmetic only. It does not infer that account quotas imply
safe request rates or that a source copy has identical retrieval quality.
