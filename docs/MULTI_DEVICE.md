# Multi-device deployment

Use the same repository revision on every computer, but keep credentials, config, projections, and scheduler state local.

Recommended layout:

- One stable `Device` value per computer.
- One NotebookLM notebook per device during burn-in and normal operation.
- Separate `work` and `personal` auth profiles on each computer.
- A 15-minute scheduler per device with a 60-minute quiet gate and six-hour hard ceiling.
- Cross-notebook querying only after each device independently passes projection, reconciliation, and retrieval gates.

Do not sync `%USERPROFILE%\.notebooklm` or `%USERPROFILE%\.codex\thread-rag` through Git. Authenticate each computer directly. This prevents one machine from inheriting another machine's durable credential or corrupting revision lineage.

If a task is renamed, the stable task ID keeps lineage intact and the next projection records the new title. If an old task is updated, its `updatedAt` change makes it eligible after the quiet gate (or hard ceiling), so it does not require a daily full rebuild.

Before promoting a full corpus, estimate projected source count. Each split part consumes one NotebookLM source, and source limits are live account properties. Shard by device/time/project or add deterministic packing rather than silently dropping tasks.
