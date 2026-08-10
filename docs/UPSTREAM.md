# Upstream notebooklm-py boundary

This repository is a consumer and operational wrapper of [teng-lin/notebooklm-py](https://github.com/teng-lin/notebooklm-py). It pins v0.8.0 in `pyproject.toml` and commits the complete hash-bearing `uv.lock` graph so upstream protocol, return-shape, or transitive dependency changes cannot silently alter synchronization behavior. The `notebooklm` CLI is the primary user and agent control surface.

## Responsibility map

| Surface | Upstream `notebooklm-py` | This repository |
|---|---|---|
| Google/NotebookLM protocol | Undocumented RPC transport and models | No protocol reimplementation |
| Python | `NotebookLMClient` | Projection-aware sync, reconciliation, retrieval, and benchmarks |
| CLI | Profiles, login, auth checks, notebooks, sources, limits | Primary operator interface plus safe PowerShell orchestration for `personal` and `work` profiles |
| MCP | General NotebookLM MCP server | Optional secondary adapter; not the default operator or synchronization interface |
| Authentication | Browser capture, stored cookies, master-token re-mint | Exact-account checks, profile separation, ACL locking, scheduled refresh policy |
| Codex data | No Codex-specific behavior | Visible-message projection, redaction, splitting, provenance, and local verification |

## Authentication model

NotebookLM has no public API key, public OAuth scope, or service-account flow. `notebooklm-py` authenticates with Google session cookies captured from a real browser. For unattended operation, its master-token flow stores a durable credential in `master_token.json` and uses it to re-mint web cookies after an ordinary session expires.

The thread-RAG deployment uses two explicit profiles:

- `personal` for the intended personal Google identity;
- `work` for the intended work Google identity.

Each profile lives under `%USERPROFILE%\.notebooklm\profiles`, must match its expected email, and must be ACL-restricted to the current Windows user and `SYSTEM`. The MCP server and CLI reuse these profiles; they do not maintain separate authentication stores.

Scheduled refreshes use `notebooklm -p PROFILE auth refresh --verify`, not an unconditional master-token re-mint. This lets one policy work for both durable master-token profiles and browser-session-only Workspace profiles. A Workspace account that rejects the master-token exchange remains usable through the CLI, but cannot promise fully unattended recovery after its organization expires the browser session.

## Interface priority

Use interfaces in this order:

1. Use the `notebooklm` CLI for login, profile selection, notebook/source management, diagnostics, limits, chat, research, and artifacts.
2. Let thread-RAG scripts use the pinned Python API internally for revision swaps, source-ID lineage, local checkpoints, and deterministic validation.
3. Use `notebooklm-mcp` only when an MCP host specifically needs NotebookLM tools.

The MCP server is installed so the capability is available, but it is not the main user path and is not the synchronization authority.

## Upgrade procedure

1. Review the upstream release notes and migration guide.
2. Use `uv add` to update the exact version in `pyproject.toml`/`uv.lock`, then update every versioned runtime path together.
3. Install into a clean isolated Codex root.
4. Run the complete offline suite.
5. Run passive live checks for both profiles; do not refresh credentials during a diagnostic probe.
6. Test `auth refresh --verify` for both profiles, plus browserless master-token renewal for every profile that requires fully unattended recovery.
7. Run a bounded disposable-notebook projection, upload, reconciliation, and retrieval benchmark.
8. Promote the new global skill only after all release gates pass.

CI exports the locked runtime graph with hashes and audits it with `pip-audit`. GitHub Actions are pinned to immutable commits, and Dependabot waits seven days before proposing new dependency releases.

Never point production synchronization at an unpinned checkout of upstream `main`.
