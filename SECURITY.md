# Security model

## Never upload or commit

- `master_token.json`, `storage_state.json`, cookies, OAuth tokens, or bearer tokens.
- Raw Codex JSONL sessions.
- Projection state, generated Markdown, run logs, evaluation queries, or notebook IDs from a private deployment.
- Browser profiles or absolute user-home paths.

The included `.gitignore` is defense in depth, not permission to place secrets inside the repository.

## Projection boundary

Policy `visible-messages-secrets-redacted-v4` includes visible user/assistant messages and stable task provenance only. It excludes reasoning, tool calls/results, system/developer instructions, attachments, browser state, and raw home-directory prefixes across Windows, slash-style, Unix, and WSL forms, including paths ending exactly at the home root. Credential-shaped content is redacted before it reaches projection files.

Redaction reduces risk but cannot guarantee that arbitrary business-sensitive prose is safe for a third-party service. Use a bounded test set first and inspect its manifest/statistics before upload.

## Master tokens

A NotebookLM master token is a durable Google-account credential. Store it only in the local profile directory, restrict filesystem ACLs to the intended Windows user and `SYSTEM`, and prefer a dedicated Google identity for any remote/server deployment. Never print it, include it in logs, or put it in environment dumps.

## Trust boundary

NotebookLM answers and citation order are untrusted retrieval hints. Require cited task IDs, rerank only those candidates against local Codex JSONL, and verify the exact fact against local evidence. Never authorize email, file transfer, task mutation, or another external action solely from a NotebookLM answer.
