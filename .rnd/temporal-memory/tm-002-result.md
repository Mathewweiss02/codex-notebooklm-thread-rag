# TM-002 Result

## What was run

- Verified Node 24.11.1 exposes `node:sqlite`, but the runtime marks it experimental.
- Verified the pinned NotebookLM Python runtime is Python 3.12.4 with SQLite 3.45.3.
- Ran the synthetic file-backed SQLite spike at 1,000, 5,000, and 20,000 events for three content-placement modes.
- Ran a Node in-memory SQLite comparison at the same scales.

## Evidence summary

| Mode | 1K build/query/context ms | 5K build/query/context ms | 20K build/query/context ms | 20K bytes |
| --- | --- | --- | --- | ---: |
| Text in SQLite | 67.876 / 1.676 / 0.035 | 95.051 / 8.100 / 0.036 | 373.760 / 33.438 / 0.065 | 6,434,816 |
| Metadata + sidecar | 33.778 / 1.654 / 41.473 | 82.314 / 6.356 / 35.188 | 359.749 / 31.363 / 41.915 | 6,375,338 |
| Content-addressed blobs | 44.619 / 1.453 / 2,338.710 | 84.359 / 6.237 / 3,523.411 | 418.677 / 30.235 / 3,482.171 | 7,825,802 |

The context sample was 100 selected messages. These are synthetic directional measurements, not production-corpus guarantees.

Node's experimental in-memory SQLite comparison measured 20,000-row build/query of 222.247/12.912 ms, but that does not include durable-file behavior, migration, recovery, or an unpinned Node compatibility contract.

## Result

The hypothesis is strengthened. The selected architecture is Node parser → versioned redacted event handoff → pinned Python SQLite index, with sanitized text in SQLite. This preserves the strongest existing contract and avoids making an experimental Node database API a release dependency. Content-addressed blobs are rejected as the default due to read latency and file-management overhead.

## Limitations

- The spike used synthetic rows, not private corpus text.
- Process handoff and full Node parser throughput are not yet measured.
- SQLite crash, migration, corruption, and disk-full behavior belong to TM-003/TM-004 and remain release gates.
- The sidecar option may become useful under a measured disk/privacy constraint, but it is not the default.

## Next move

Advance `TM-002` to done and start `TM-003`: implement the versioned canonical-event extractor/handoff and independent oracle-parity tests. Keep the index itself behind the TM-004 dependency.
