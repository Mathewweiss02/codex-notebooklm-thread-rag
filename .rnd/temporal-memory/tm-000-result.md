# TM-000 Result

## Experiment

- ID: `TM-000`
- Title: Freeze current baseline and private temporal oracle fixtures

## What was run

- The existing repository suite was run from the current working tree.
- A read-only app-server inventory was generated and reduced to aggregate counts and a task-ID fingerprint.
- Three identical local semantic-search timing runs were measured without NotebookLM hydration.
- The synthetic independent temporal oracle was run against `fixtures/oracle-fixtures.json`.

## Evidence

- Existing suite: passed, with 22 Node tests and 60 Python tests.
- Live visible-task inventory: 140 tasks.
- Registered config roles: one retrieval and one persistent chat.
- Local search timing: 1315.21–1402.14 ms across three runs.
- Oracle fixture: 14 records, 9 canonical visible timestamped records after role/timestamp filtering and active/archive deduplication; 4/4 cases passed.
- Oracle result digest: `1374348f89aa011c236678e2c9796ac14f70836c96d19b392b564f305d3a2e84`.

## Result

The hypothesis is strengthened. The existing suite is reproducible, the live corpus is measurably different from the stale README baseline, and the temporal invariants can be represented in a small synthetic corpus without private data. The result does not authorize feature implementation by itself; the next required item is contract approval.

## Next move

Advance `TM-000` to complete after rerunning the oracle and filling its deterministic digest. Then begin `TM-001`: approve versioned event, time-range, context-pack, and verification contracts.
