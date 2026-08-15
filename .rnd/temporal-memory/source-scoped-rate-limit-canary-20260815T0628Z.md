# Source-scoped cooldown canary — 2026-08-15T06:28Z

- Policy: `generalization-v1`; one development case; disposable retrieval notebook only.
- Transport retries: `0`; semantic attempts: `1`; candidate width: `80`.
- Result: one classified NotebookLM rate-limit event after approximately 7.6 seconds.
- Scope: zero scope violations; persistent CLI chat was not touched.
- Quality: no candidate-recall or Top-1 quality score counted. This is fail-closed transport evidence, not a benchmark pass or fail.
- Causal boundary: the upstream throttle remains the observed cause; the live quality gate is still unmeasured until a clean post-cooldown run completes.
- Private report digest: `4495bf565cc22caf439c773abd43426712eefdbf416ed41f8bff393d5982e87a`.
