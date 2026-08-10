# Decisions

- Keep NotebookLM as the current semantic backbone because it is already functional and economically attractive; treat alternatives as measured challengers, not assumptions.
- Keep the NotebookLM CLI as the primary human interface. Python remains internal orchestration and MCP remains optional.
- Separate persistent CLI conversation notebooks from dedicated disposable retrieval notebooks.
- Keep credential redaction mandatory for every remote NotebookLM upload and query. Explore any user-controlled trust mode only for local-only retrieval surfaces.
- Preserve an explicit enrolled scope as the safety boundary, but automate its capacity-aware update so new eligible tasks cannot disappear silently.
- Treat reconciliation as strict for dedicated retrieval notebooks: extras are errors to investigate, never automatic deletion targets.
- Make retention dry-run-first and lineage-aware, then allow scheduler application only after tests and live reconciliation pass.
- Do not merge the draft PR until health truth, automatic enrollment, conversation isolation, strict reconciliation, retention, CI, dependency, documentation, and benchmark gates are satisfied.
- Use a radar chart only from recorded metric evidence; unknown axes remain unknown rather than receiving invented scores.
- Fuse NotebookLM semantic rank, query-to-title overlap, and normalized local evidence; never discard a cited candidate merely because active/raw local history cannot verify it.
- Treat equivalent sibling tasks as explicit multi-ID benchmark ground truth instead of scoring one valid result as a miss.
- Reject stateless full-corpus reshuffling as the multi-notebook growth model; require sticky shard ownership and a recall-gated local router before scaling past one notebook.
