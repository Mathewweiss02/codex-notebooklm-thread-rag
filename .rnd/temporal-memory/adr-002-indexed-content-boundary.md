# ADR-002: Indexed Content Boundary

Status: accepted for implementation spikes

Date: 2026-08-14

## Decision

Store sanitized message text in the derived SQLite index alongside message identity, timestamp, thread, digest, and source provenance. Canonical Codex JSONL remains the authority; SQLite text is a redaction-policy-versioned cache used for fast context assembly.

Never store raw credentials, raw home paths, tool payloads, reasoning, or attachments in the derived index. A redaction-policy change invalidates the index and requires a full rebuild before use.

## Options considered

### Sanitized text in SQLite — selected

At 20,000 synthetic events, build time was 373.760 ms, indexed query time was 33.438 ms, and reading a 100-message context sample took 0.065 ms. The measured footprint was 6,434,816 bytes. Text is available in the same atomic snapshot as its temporal metadata, which simplifies provenance and crash recovery.

### Metadata plus one content sidecar

At 20,000 events, build time was 359.749 ms, query time was 31.363 ms, context read was 41.915 ms, and footprint was 6,375,338 bytes. It saves only a small amount of space in this fixture but adds offset validity, sidecar retention, and two-artifact atomicity concerns. Keep it as a future low-disk experiment, not the default.

### Content-addressed blobs

At 20,000 events, build time was 418.677 ms, query time was 30.235 ms, context read was 3,482.171 ms, and footprint was 7,825,802 bytes. The many-file read path is too slow and operationally noisy for the default context path. A blob cache could be reconsidered only with measured batching and bounded retention.

## Consequences

Positive:

- Context packs can read evidence from one verified transactionally committed state.
- Provenance and text cannot drift because they are versioned together.
- The local temporal path remains fast enough to be the first answer surface.

Costs and mitigations:

- Derived storage duplicates sanitized text; retention and ACL checks must cover the index.
- Rebuilds are required after redaction-policy changes.
- Full text is still not canonical; every result retains source-file digest and line provenance for verification.

## Revisit triggers

Reopen this ADR if real-corpus disk growth, privacy review, secure deletion, or process-handoff measurements show the duplication is unacceptable, or if a batched content cache can beat the default without weakening atomicity.
