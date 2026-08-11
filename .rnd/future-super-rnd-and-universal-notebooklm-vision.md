# Parked vision: recursive super-R&D template and universal NotebookLM capability

Status: **idea capture only**

Captured: 2026-08-10

Implementation authority: **none yet**

This note preserves the user's complete direction without turning it into an active workstream. Do not scaffold a global skill, launch recursive tasks, ingest the speculative source corpus, or change the NotebookLM production architecture from this note alone. Resume only after discussing the model, researching the practical alternatives, and receiving a clear implementation request.

## 1. Core ambition

Create a reusable, global “super” research-and-development skill for large optimization problems. It should begin with unusually broad and deep research, produce plans for the plans, expose every meaningful quality that can improve, and support disciplined recursive experiments until both quantitative and qualitative promotion gates are met.

The intended feeling is not a linear checklist. It is a living system whose research areas can subdivide, run focused experiments, feed evidence back to the whole, revisit weak dimensions, expand when new bottlenecks appear, and continue improving without allowing one highly optimized metric to conceal weakness elsewhere.

This is meant for substantial systems such as the Codex-to-NotebookLM retrieval stack. It is not meant for a narrow repair such as hiding a scheduled terminal window.

## 2. User-provided structural metaphors to preserve

These are design inspirations and memory aids, not validated mathematical or scientific requirements:

- A character-selection radar chart whose axes include every important capability; the long-term aim is “Super Saiyan God / Ultra Instinct” balance rather than one exaggerated stat.
- Muay Thai or MMA training adaptations: cycle among all major dimensions so each remains strong while the whole system compounds.
- A warehouse containing specialized warehouses: one parent R&D program with many autonomous but coordinated research domains and micro-R&D trails.
- A recursively divisible square or multiverse: begin with a broad map, divide it into four, divide each child again, and continue to whatever depth the evidence requires (`4^n`).
- An optional 64-quadrant starting canvas for very large projects. Sixty-four is a candidate scaffold, not a quota; smaller systems should not invent empty quadrants just to fill a template.
- Three-dimensional radar-chart, spiral, toroid, “wheel within a wheel within a wheel,” sacred-geometric, vortex-based-mathematics, and plasmoid imagery as possible ways to think about nested feedback and cyclical flow.
- A dedicated untouched branch/folder for the VBM/toroidal line of thought so speculative inspiration is not silently mixed into validated engineering.

Any future implementation must clearly separate metaphor, hypothesis, empirical observation, and established mechanism. Geometry should earn its place by making the research easier to reason about or operate; it must not be treated as proof.

## 3. Candidate future source corpus

The user may already have a local Malcolm Bendall folder, PDFs described as available from the “Star Force” website, and transcripts associated with “Alchemical Science.” These may be useful for a separately labeled exploratory branch about toroidal/VBM/plasmoid concepts.

Do not search for, ingest, endorse, or operationalize these materials yet. If resumed, first locate the exact materials, confirm names and provenance with the user, evaluate source quality, and keep speculative claims isolated from the evidence base used for software architecture.

## 4. Functional requirements for the future R&D template

### 4.1 Broad-to-deep discovery

- Start wide enough to identify paradigm-level choices, hidden assumptions, bottlenecks, and “six versus ace” decisions before tuning local details.
- Map the system, actors, interfaces, constraints, failure modes, external dependencies, and unknowns.
- Ask whether the foundational approach is still the best available option, while recognizing that NotebookLM currently appears to be a strong/free RAG backbone.
- Subdivide only when a branch has a clear question, owner, dependency, expected evidence, or measurable outcome.

### 4.2 Recursively decomposable factor model

- Represent every improvement area as a factor with parent/child lineage.
- Permit factors to split into smaller factors at runtime when research uncovers meaningful structure.
- Support multiple levels: whole system, capability domain, bottleneck, hypothesis, experiment, and implementation detail.
- Preserve cross-links when one experiment affects several axes; do not force reality into a strict tree when it is a graph.
- Maintain an explicit “unknown unknowns / frontier discovery” lane so the map can expand instead of merely optimizing its initial assumptions.

### 4.3 Measurable improvement

Each active factor should eventually define:

- the desired capability and why it matters;
- quantitative metrics where honest measurement is possible;
- qualitative rubrics with anchored examples and independent review where numbers are incomplete;
- a baseline, target, confidence level, and uncertainty;
- constraints and anti-goals;
- candidate interventions;
- expected benefit, cost, risk, and reversibility;
- test method, controls, sample size, and stopping rule;
- evidence provenance and artifact locations;
- promotion, rollback, and maintenance gates.

Do not manufacture numbers for inherently qualitative properties. Do not leave measurable properties as vague adjectives.

### 4.4 Recursive experiment engine

- Turn mature hypotheses into bounded experiment packets that can be handed to isolated Codex tasks or other workers.
- Allow a task to run repeated trials until a predeclared threshold, budget, confidence condition, futility boundary, or safety stop is reached.
- Feed results back into factor scores, the research queue, and parent decisions.
- Automatically propose follow-up questions when evidence reveals a new bottleneck, but require appropriate authority before expanding scope or making consequential changes.
- Rotate attention toward the weakest or highest-leverage axes rather than repeatedly polishing the easiest benchmark.
- Revalidate previously strong axes after changes elsewhere; optimization is a spiral with regression checks, not a one-way staircase.

### 4.5 Scientific and benchmark integrity

- Use objective scoring contracts, frozen cases, development/validation/holdout separation, provenance, and reproducible run artifacts.
- Guard against false positives, false negatives, leakage, cherry-picking, post-hoc relabeling, benchmark overfitting, and Goodhart's law.
- Distinguish discovery metrics from final-answer correctness. For retrieval, candidate recall, accepted Top-1, abstention, citation validity, factual verification, latency, and cost are different axes.
- Require repeated runs and uncertainty estimates where nondeterminism matters.
- Keep failed and null experiments; negative evidence should prune branches instead of disappearing.
- Periodically challenge the benchmark itself with adversarial cases, blinded review, and new sealed holdouts.
- Never claim recursive “training” if the system is actually configuration search, prompt/organization optimization, reranking, or software iteration. Name the learning mechanism precisely.

### 4.6 Balanced scorecard / radar operation

Potential top-level axes include accuracy, recall, precision, abstention, evidence quality, latency, throughput, freshness, reliability, resilience, scale, operability, simplicity, maintainability, security/privacy, cost, portability, user experience, and adaptability.

The final axes must be derived per project rather than copied mechanically. The orchestration policy should make tradeoffs visible, define minimum floors, prevent regressions below those floors, and identify a Pareto frontier when every metric cannot be maximized simultaneously.

### 4.7 Plans for plans

The future skill may need layered artifacts:

1. charter and boundary;
2. system map and factor ontology;
3. evidence/source map;
4. prioritized research portfolio;
5. experiment queue and dependency graph;
6. individual micro-R&D packets;
7. result ledger and decision log;
8. multidimensional scorecard;
9. implementation handoffs;
10. regression, maintenance, and frontier-discovery loops.

The template should remain lean in actual use: complex state belongs in files and scripts, while the installed skill should give a fresh Codex task concise triggers, do/don't guidance, decision rules, examples, and commands.

## 5. Universal NotebookLM capability vision

The current repository is centered on Codex task retrieval, but the desired installed skill should eventually make a fresh Codex task fluent with NotebookLM more generally.

### 5.1 Scope

- Continue treating the CLI as the primary user and automation interface; MCP remains optional rather than the main path.
- Work with arbitrary user notebooks, not only synchronized Codex-task notebooks.
- Make notebook discovery, selection, authentication/profile choice, querying, citation handling, and local verification feel seamless from a context-free Codex task.
- Preserve ordinary notebook conversation history by default. Disposable resets belong only to explicitly designated retrieval/benchmark notebooks.
- Consider a custom MCP only if measured ergonomics or capability gaps justify its extra maintenance; do not build one merely because it is possible.

### 5.2 Query decomposition and fan-out

- When one large prompt contains many independent information needs, split it into clear atomic questions rather than assuming one overloaded answer will retrieve everything well.
- Research safe parallelism across independent notebooks, isolated replicas, or explicit conversations.
- Do not naïvely race asks against one notebook's mutable current conversation.
- Measure concurrency limits, throttling, server behavior, CPU/network use, failure isolation, citation mapping, and quality as batch size grows.
- Return a coherent synthesis only after each atomic result is attributed and verified.
- Make single-query latency excellent as well; batching must not become an excuse for a slow everyday path.

### 5.3 Reliability and truthfulness

- Keep “candidate found” separate from “accepted as correct.” The observed packed smoke test found all four candidates but accepted only three as Top-1; that is `4/4` candidate recall and `3/4` accepted Top-1, not a perfect result.
- Avoid invisible retry latency. Expose whether a result was first-pass, retried, degraded, rejected, or locally recovered.
- Offer explicit modes such as fast interactive lookup and reliability-oriented lookup, each with bounded retry/time budgets.
- Never return an unverified candidate as fact merely to avoid an abstention.
- Benchmark normal usage with clean or controlled conversation state so accumulated notebook history does not silently bias results.

### 5.4 Skill ergonomics

- A fresh Codex task should be able to invoke the capability without knowing the repository's history.
- Keep the main skill concise and high-signal; move implementation detail into references and scripts.
- Include strong examples, decision rules, profile/notebook safety checks, conversation-state rules, and clear recovery paths.
- Prefer a few composable commands over an ever-growing collection of overlapping entry points.
- Treat “it just works like butter” as an operability target that must be tested with cold-start task scenarios.

## 6. Explicit current boundary

For the present workstream:

- Fix the recurring 15-minute Windows terminal popup while keeping synchronization active and observable.
- Keep the NotebookLM system lean, healthy, and honest about latency, retries, and retrieval quality.
- Do not create the global super-R&D skill or a 64-cell template now.
- Do not launch recursive experiments, multi-task swarms, a new MCP, or a new NotebookLM architecture now.
- Discuss the desired operating model before selecting the next large experiment.

## 7. Re-entry questions for a future conversation

Before implementation, answer:

1. Is the deliverable a global Codex skill, a generic `.rnd` workspace generator, an experiment orchestrator, a visualization, or a layered combination?
2. Which parts must be automated, and which decisions must remain human-gated?
3. Is 64 a useful default canvas, an optional visualization, or only a metaphor?
4. What is the smallest project that can validate recursive subdivision and balanced optimization without creating bureaucracy?
5. How will independent holdouts and qualitative review prevent recursive benchmark gaming?
6. What permissions, time budgets, and stop conditions may spawned tasks receive?
7. What evidence would justify toroidal/fractal organization over a conventional dependency graph plus scorecard?
8. Which universal NotebookLM capability should be proven first: cold-start usability, atomic prompt decomposition, parallel fan-out, single-query latency, or cross-notebook synthesis?
