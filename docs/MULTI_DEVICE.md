# Multi-device deployment

Use the same repository revision on every computer, but keep credentials, config, projections, and scheduler state local.

On each computer:

1. Clone the repository and run `install.ps1`; this installs the pinned runtime and global Codex skill.
2. Capture and verify that computer's `work` and/or `personal` profile. Never copy `.notebooklm` from another machine.
3. Create a unique stable `Device` value and a bounded notebook/config.
4. Pass the clean-install, privacy, auth, reconciliation, retrieval, and scheduler gates independently.
5. Share the NotebookLM notebook with the other intended Google identity only when cross-account discovery is required.

Recommended layout:

- One stable `Device` value per computer.
- One dedicated retrieval notebook per device during burn-in and normal operation, plus an optional independently synchronized CLI-chat notebook when persistent conversation history is required.
- Separate `work` and `personal` auth profiles on each computer.
- A 15-minute scheduler per device with a 60-minute quiet gate and six-hour hard ceiling.
- Cross-notebook querying only after each device independently passes projection, reconciliation, and retrieval gates.

Do not sync `%USERPROFILE%\.notebooklm` or `%USERPROFILE%\.codex\thread-rag` through Git. Authenticate each computer directly. This prevents one machine from inheriting another machine's durable credential or corrupting revision lineage.

The Git repository contains code, tests, the installer, documentation, and the global skill definition. It must never contain account emails, notebook/task IDs, auth files, private queries, projections, run reports, or machine-local configs.

If a task is renamed, the stable task ID keeps lineage intact and the next projection records the new title. If an old task is updated, its `updatedAt` change makes it eligible after the quiet gate (or hard ceiling), so it does not require a daily full rebuild.

Before promoting a full corpus, estimate projected source count. Each split part consumes one NotebookLM source, and source limits are live account properties. Shard by device/time/project or add deterministic packing rather than silently dropping tasks.
