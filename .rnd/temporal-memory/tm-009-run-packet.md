# TM-009 Run Packet

## Mission

Make the installed skill route broad temporal requests to the unified local
temporal CLI from a fresh task, while retaining NotebookLM for vague semantic
candidate discovery only.

## Cold-start cases

The route table covers:

- broad recap: “What was I doing yesterday?” → `recap`;
- period find: “When did I ask for the refactor?” → `find`;
- deep context: “Load the deep context from last week” → `context`;
- separate delta: “What changed between Tuesday and Wednesday?” → `compare`;
- pure period semantics: “What does yesterday mean in my timezone?” → `when`;
- vague semantic memory without a broad period → `notebooklm_thread_search.py`.

## Method

1. Keep the route table in `references/temporal-routing.json`.
2. Link it from the installed skill and provide operational examples in
   `references/temporal-memory.md`.
3. Assert the broad-temporal precedence rule and every cold-start route in an
   executable Python test.
4. Run the existing skill-install integration and full repository suite.

## Stop condition

Any broad temporal case routed to semantic-only NotebookLM, any missing index
reported as empty, or any persistent-chat reset blocks promotion.
