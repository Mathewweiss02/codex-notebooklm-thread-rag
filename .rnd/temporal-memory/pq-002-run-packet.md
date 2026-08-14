# PQ-002 Run Packet: Conversation-isolation discovery

## Objective

Determine whether the installed CLI can provision independent NotebookLM
conversation pools without deleting or contaminating the persistent human
chat conversation. This is a read-only discovery gate; no new notebook and no
conversation reset is authorized.

## Evidence surfaces

1. The configured `NotebookLmCli` path for both live configs.
2. Pinned CLI help for `ask`, `history`, and `status`.
3. The installed v0.8.0 source for conversation selection, locks, and the
   public client surface.
4. Aggregate-only read-only profile/status/history checks.

## Questions

- Does `--new` create an independent conversation or replace current state?
- Can the CLI list or allocate multiple server-side conversation IDs without
  deleting the current conversation?
- Does an explicit conversation ID provide isolation, or only continuation of
  an already existing conversation?
- Are upstream RPC limits equivalent to safe same-notebook chat concurrency?

## Safety boundary

- Do not run `ask --new` against any live notebook in this packet.
- Do not print or persist notebook IDs, conversation IDs, questions, answers,
  citations, cookies, or auth material.
- Treat the persistent `chat` notebook as user-owned state.
- Treat the `retrieval` notebook's disposable reset as an isolated existing
  behavior, not a general concurrency primitive.

## Decision gate

Pass only if a non-destructive provisioning path is documented, repeatable,
and independently verifies conversation identity and no cross-talk. A client
RPC semaphore or a successful transport call alone does not pass this gate.
