# PQ-002 Result

## Findings

- Both configured sync surfaces point to the pinned isolated `notebooklm-py`
  0.8.0 CLI. The bare PATH command on this machine resolves to an older 0.6.0
  executable; it is not the configured production path and must not be used
  for this system.
- `ask` defaults to the notebook's most recent conversation.
- `ask --conversation-id` resumes one already-known conversation ID; the CLI
  exposes no public command to list or allocate a reusable conversation pool.
- `ask --new` explicitly deletes the notebook's current server-side
  conversation before asking. The help text and source both mark this as
  destructive and unrecoverable. JSON mode implies confirmation, so a scripted
  call is still destructive rather than safely isolated.
- `history` reads the most recent conversation; it is not a conversation-pool
  manager.
- The v0.8.0 client has a global RPC ceiling (default 16), per-notebook locks
  for new-conversation creation, and per-conversation locks for follow-ups.
  These are transport/state-race controls, not proof that multiple asks on one
  notebook are independent. Requests without an explicit conversation ID use
  the notebook's mutable current conversation.
- Read-only live checks for the pinned CLI completed successfully for profile
  listing, current context status, and chat-history retrieval. The probe kept
  IDs and content out of its output.

## Decision

Reject same-notebook `--new` fan-out and naïve same-notebook parallel asks as
production strategies. They can delete current history, queue behind shared
state, or race the server's mutable current conversation. Keep the persistent
CLI chat notebook untouched.

An explicit existing conversation ID remains a possible transport primitive,
but the CLI does not provide safe non-destructive provisioning for a pool of
such IDs. Do not claim same-notebook parallelism until that gap is closed by a
separate, documented upstream capability.

## Next gate

Advance to PQ-003: model isolated notebook replicas and their source-freshness,
capacity, cleanup, and cost implications without creating live replicas.
