# ADR-001: Temporal Index Engine and Language Boundary

Status: accepted for implementation spikes

Date: 2026-08-14

## Decision

Reuse the existing Node canonical event extractor, emit a versioned `temporal-event-v1` NDJSON handoff, and maintain the derived temporal index with the pinned Python 3.12 runtime's stdlib `sqlite3`.

The handoff is an atomic per-run artifact, not a long-lived unauthenticated service. The indexer validates the contract version, event identities, source policy, and run digest before opening a write transaction. A failed parse or incomplete handoff leaves the previous committed index untouched.

## Options considered

### Node parser plus Node `node:sqlite`

Node 24.11.1 exposes `node:sqlite` and a 20,000-row in-memory microbenchmark measured 222.247 ms to insert and 12.912 ms to query 6,667 rows. It is not selected as the production foundation because Node reports the module as experimental and this repository does not pin a Node runtime or SQLite API compatibility level. The raw speed is useful as a future comparison ceiling, not a stability guarantee.

### Node parser plus Python stdlib SQLite — selected

This preserves one visibility/redaction implementation, uses the already pinned Python 3.12 runtime, and uses SQLite 3.45.3 without adding a database dependency. The 20,000-row file-backed spike built in 359.749–373.760 ms and queried 6,667 rows in 31.363–33.438 ms depending on content mode. It has an explicit process-handoff cost, which TM-003 will measure and bound.

### Python-only parser plus SQLite — rejected

It would avoid the process handoff but duplicate the existing Node parser's visible-role, compaction, overflow, truncation, redaction, and deduplication semantics. That violates the contract and creates language-drift risk.

### Flat files or a custom manifest — rejected as the primary query engine

They can remain canonical input or recovery artifacts, but they do not provide the required indexed time/thread queries, migrations, atomic transactions, integrity checks, or bounded concurrent readers without rebuilding database behavior manually.

## Consequences

Positive:

- One canonical visibility/redaction parser remains authoritative.
- SQLite gives indexed timestamp/thread lookup, atomic transactions, integrity checks, and migrations.
- The existing pinned runtime and Python test surface remain usable.
- The handoff is inspectable, hashable, and easy to fuzz before commit.

Costs and mitigations:

- A Node-to-Python process boundary adds startup and serialization latency; measure it in TM-003 and reject the design if it violates warm/cold floors.
- The index is derived state and must never be treated as canonical; rebuild and last-known-good rules are mandatory.
- The handoff must never contain unredacted text or raw paths.

## Revisit triggers

Reopen this ADR if the process handoff exceeds the performance budget, the pinned Python runtime cannot provide the required Windows SQLite behavior, or a future project revision pins a stable Node SQLite API and proves equivalent recovery/migration behavior.
