# X-RAY — BUILD SPECIFICATION
### Hack Hydra · Track 01 · Enterprise Context + Ontology

**This document is the complete brief. Build what it describes.** It contains the intent, the competitive reasoning, the engine's hard constraints, the exact data model, every query, the algorithms, the evaluation plan, the demo, and the fallbacks. Read all of Part 1 before writing any code — the engine has restrictions that will silently break naive implementations.

---

# PART 1 — CONTEXT AND CONSTRAINTS

## 1.1 What we are building, in one sentence

A system that reads a company's Slack, email, tickets and code, and draws **the organization as it actually is** — who really holds it together, where it is structurally about to break, and what records someone deleted.

## 1.2 The thesis

The enterprise dataset for this track is treated by everyone as *one* corpus of documents to be searched. It is not. It contains **two independent graphs layered on top of each other**:

1. **The work graph** — modules, tickets, commits, and their technical dependencies.
2. **The human graph** — who talks to whom, who replies to whom, who reviews whose code.

Nobody separates them. Every other team in this track will build entity resolution and retrieval over the corpus as a flat document pile. We build both graphs and then study **the relationship between them**. Three findings come out of that, and each is invisible to the flat-document approach:

| Lens | Question | Finding |
|---|---|---|
| **Ghost** | Who is structurally load-bearing? | The real org chart — often a mid-level person nobody has flagged |
| **Faultline** | Where does technical dependency exist without human coordination? | The specific file pairs where the next failure appears |
| **Spoliation** | Where does the graph structurally require a record that isn't there? | Evidence of deletion |

## 1.3 Why this wins the track

Judging is **two-stage**: entries are ranked within their track first, and **only the top entry per track advances** to the final. You are not competing against the whole field — you are competing against everyone else in Track 01 for one slot.

- **Every other Track 01 entry will do entity resolution** ("is Sam the same person as @soham"). It's the brief's headline example. We are asking a question nobody else asks.
- **Track 01 has the lowest published ceiling in the event.** The best agentic RAG result on the Salesforce HERB benchmark is **32.96**. Beating a stated number is a result a judge verifies in ten seconds.
- **The demo is uncomfortable in the way great demos are.** A judge does not think "nice graph." They think "who is the load-bearing person at *my* company, and does my VP know?"

Judging criteria, and how we hit each:

| Criterion | How we address it |
|---|---|
| Technical execution | Two graphs, three analyses, one ingest pipeline, working UI |
| **Use of HydraDB and graph-native approaches** | ~65% of the system is bounded path traversal in the engine. This is the criterion most entries fail, and also what the separate $500 "Best Use" award rewards. |
| Product completeness and usability | One-command setup, a real UI, a judge can run it |
| Quality of results | Measured against HERB's 32.96 and against a churn-based baseline |
| Originality | The core question has no prior art in this exact form |

## 1.4 The risk, stated honestly

Faultline's underlying claim — that technical-dependency-without-communication predicts defects — is **contested in the literature**.

- **For:** Cataldo et al., IEEE TSE 35(6), 2009 (DOI 10.1109/TSE.2009.42) found combined code+developer networks predict failures better than code metrics alone. Bird et al., ISSRE 2009 found the same on Windows Vista and Eclipse. Cataldo's ESEM 2008 framework reports coordination congruence reduced modification-request resolution time by ~32%.
- **Against:** Mauerer et al., IEEE TSE 2021 (arXiv 2105.08198) analyzed 25 large open-source projects and found **no** relationship between socio-technical congruence and defects or churn.

**This is why X-Ray has three lenses instead of one.** If Faultline's predictive effect does not appear in our data, Ghost and Spoliation still carry the entire demo, and we reframe Faultline from "predicts the next bug" to "reveals coordination debt" — which is descriptively true regardless. **The project cannot fail on this axis.** Build it this way deliberately.

## 1.5 Engine constraints — READ BEFORE WRITING ANY QUERY

We build on the **open-source engine** at `github.com/hydra-db/hydradb`. A separate hosted product exists at `api.hydradb.com` with vector search, embeddings, and connectors — **that is a different system and is not what is judged. Do not use it.**

The open-source engine is Rust, AGPL-3.0, an object-store-native graph database on SlateDB over S3-compatible storage, with SuiteSparse GraphBLAS traversal, Bolt 5.x (Neo4j drivers work), and an HTTPS API at `POST /v1/graphs/{graph}/query`.

**It has no vector index, no embeddings, no semantic search, no BM25, no full-text index, no temporal types, and no transactions.**

### Cypher subset — violations are parse errors

| Area | Rule |
|---|---|
| Node matching | **Integer `id` only.** A node with labels or non-id properties must be named. |
| `WHERE` | Only `=`, `<>`, `<`, `>`, `<=`, `>=`, `STARTS WITH`. **No `IN`, `CONTAINS`, `ENDS WITH`, `IS NULL`.** |
| `RETURN` | **`RETURN *` unsupported.** |
| Aggregates | `count`, `sum`, `avg`, `collect` only. **No `min`, no `max`, no `count(DISTINCT)`.** |
| `MERGE` | **id-only.** No `ON CREATE` / `ON MATCH`. |
| `WITH` | **Pass-through only** — no projection, no aliasing. |
| Variable-length paths | **Upper bound mandatory.** `*1..3` works; bare `*` and `*1..` are rejected at parse time. |
| Relationship patterns | Directed and **single-typed**. No `[:A\|B*..2]`. |
| Statements | **One per request.** No multi-statement transactions. |
| Property types | **int, float, bool, string only.** No temporal types — encode all time as integer epochs. |

**Direct consequences for this build:**
- Maintain an external `name → integer id` dictionary in the loader. Every human-readable string is stored as a *property*, never used for matching.
- "Most recent" cannot use `max()`. Sort client-side, or verify `ORDER BY … LIMIT 1` with a smoke test on day one.
- Ranking (betweenness, faultline severity) happens **client-side** from `collect()` results. The engine does the pathfinding; you do the tallying.

### Path procedures — the crown jewels

| Procedure | Shape |
|---|---|
| `algo.SPpaths` | single source → single target |
| `algo.SSpaths` | single source → all reachable |
| `algo.MSpaths` | **many sources → many targets**, with a `pairwise` mode |

Config keys: `sourceNode`, `targetNode`, `sourceLabel`, `sourceProperty`, `sourceValues`, `targetValues`, `relTypes`, `relDirection`, `maxLen`, `pathCount`.
Yields: `path`, `pathWeight`, `pathCost`.

`algo.MSpaths` executes many-source traversal **server-side in one round trip**. For "200 people → 200 people," that is one call, not 40,000. This is the single most important performance fact in the build.

**Verify the exact `relDirection` enum value in `cypher-compat.md` before writing code.** Sources disagree on whether it is `'in'`, `'incoming'`, or `'INCOMING'`.

### Performance and operational facts

- **Writes are serialized** at roughly 200–227 commits/sec, flat regardless of writer count. Bulk loading is `UNWIND $rows` batches through the Bolt/HTTP client — the in-process shard API rejects `UNWIND`. **There is no bulk loader.**
- Reads are sub-millisecond to low-millisecond **warm against local object storage**. The same cold query from a laptop to real S3 has been measured at **~27 seconds**. **Demo against local MinIO with a warm cache. Never against real S3.**
- **`export RUST_MIN_STACK=33554432`** or the node serves `/readyz` and then aborts on the first query.
- Use **`just` recipes** (`just native-check`, `just smoke`, `just minio-smoke`), never bare `cargo` — the justfile exports required bindgen/linker/stack env.
- Requires `libcypher-parser` and SuiteSparse GraphBLAS.
- **`main` is force-pushed frequently. Pin a commit and record it in the README.**
- Beyond ~3 hops on real graphs, traversal converges toward the whole connected component. Bound `maxLen` for cost *and* for meaningfulness.

---

# PART 2 — DATA

## 2.1 Source

**Primary: Salesforce HERB** (arXiv 2506.23139, EMNLP 2025 Industry; `huggingface.co/datasets/Salesforce/HERB`).
- 39,190 artifacts, 530 simulated employees, 27–30 products
- Heterogeneous sources spanning Slack-style messages, tickets, code artifacts, documents
- **Best published agentic RAG score: 32.96.** This is the number to beat.
- Roughly half the queries are unanswerable by design — which makes correct abstention worth disproportionate points.

**Secondary: EnterpriseRAG-Bench** (`github.com/onyx-dot-app/EnterpriseRAG-Bench`, arXiv 2605.05253, MIT).
- ~500,000 documents across nine sources (Slack, Gmail, Linear, Google Drive, HubSpot, Fireflies, GitHub, Jira, Confluence), 500 questions in ten categories, fictional company "Redwood Inference"

**Decision: build on HERB.** 39,190 artifacts is tractable on a serialized write path; 500,000 documents is not, within the time available. Use EnterpriseRAG-Bench only if HERB's structure turns out to lack reply/thread metadata.

## 2.2 What we extract

From each artifact we need three things:

1. **Author** — who produced it
2. **Addressee / thread parent** — who they were responding to, or which artifact this replies to
3. **Subject** — which module, product, ticket, or work item it concerns

An LLM may be used for extraction (AI coding assistants and APIs are explicitly permitted; credit them in the README). Extraction is offline and batched — it is *not* part of the query path.

**Critical design rule: no fuzzy matching ever touches the engine.** All entity resolution, name normalization, and reference linking happens in the loader, producing integer ids. The graph only ever sees exact integers.

---

# PART 3 — GRAPH DATA MODEL

All ids are non-negative integers assigned by the loader. All timestamps are integer epochs (seconds). All property values are int, float, bool, or string.

## 3.1 Nodes

```
Person {
  id: int,             // loader-assigned
  handle: string,      // display only, never matched on
  role_rank: int,      // 0=unknown, 1=IC, 2=senior, 3=lead, 4=manager, 5=director, 6=VP+
  team: int            // integer-coded team
}

Artifact {
  id: int,
  ext_ref: string,     // original dataset identifier, display only
  kind: int,           // 1=message, 2=ticket, 3=commit, 4=review, 5=doc
  created_epoch: int,
  thread_seq: int      // position in thread, -1 if not applicable
}

Module {
  id: int,
  name: string,        // display only
  product: int         // integer-coded product
}

Phantom {
  id: int,             // the referenced-but-absent artifact's id
  expected_kind: int,
  inferred_epoch: int, // bounded by neighbours
  reason: int          // 1=dangling thread parent, 2=sequence gap, 3=state transition with no record
}
```

`Phantom` is the Spoliation mechanism. See §5.3.

## 3.2 Edges

```
(:Person)-[:AUTHORED {epoch: int}]->(:Artifact)
(:Artifact)-[:REPLIES_TO]->(:Artifact)
(:Artifact)-[:ABOUT]->(:Module)
(:Person)-[:COMMUNICATES {weight: int, first_epoch: int, last_epoch: int}]->(:Person)
(:Person)-[:OWNS {confidence: int}]->(:Module)
(:Module)-[:DEPENDS_ON {weight: int}]->(:Module)
(:Artifact)-[:REPLIES_TO]->(:Phantom)
(:Phantom)-[:EXPECTED_BEFORE]->(:Artifact)
```

**`COMMUNICATES` is derived, not raw.** Build it in the loader: if Person A authored an artifact that `REPLIES_TO` an artifact authored by Person B, increment the A↔B weight. Materialize it as its own edge type so traversal is one hop per interaction rather than three. This matters — it turns a 3-hop query into a 1-hop query and makes `maxLen` budgets meaningful.

**`DEPENDS_ON` between modules** comes from co-change (two modules touched by the same commit) and from explicit references (a ticket about module X mentioning module Y). Weight = number of co-occurrences.

**`OWNS`** comes from authorship density: the person who authored the most artifacts `ABOUT` a module owns it. Store `confidence` as an integer 0–100.

## 3.3 Scale targets

| Node/edge type | Target count |
|---|---|
| Person | ~530 |
| Artifact | ~39,000 |
| Module | ~200–500 |
| Phantom | ~50–500 (whatever the data yields) |
| AUTHORED | ~39,000 |
| REPLIES_TO | ~15,000–25,000 |
| ABOUT | ~30,000 |
| COMMUNICATES | ~5,000–15,000 (deduplicated pairs) |
| OWNS | ~500–1,500 |
| DEPENDS_ON | ~1,000–5,000 |

**Total: well under 150,000 edges.** This is a small graph by design. On a serialized write path that is a decisive advantage — it should load in minutes, not hours.

---

# PART 4 — INGEST

## 4.1 Pipeline

```
HERB artifacts (JSON)
   ↓
[1] Parse + normalize        → per-artifact records
   ↓
[2] LLM extraction (batched) → author, thread parent, subject module
   ↓
[3] Entity resolution        → name → integer id dictionary (offline, fuzzy allowed here ONLY)
   ↓
[4] Derive edges             → COMMUNICATES, OWNS, DEPENDS_ON
   ↓
[5] Detect dangling refs     → create Phantom nodes
   ↓
[6] Emit NDJSON row batches
   ↓
[7] UNWIND $rows loader over Bolt → HydraDB
```

Steps 1–6 are pure offline processing. **Pre-stage everything as newline-delimited JSON before touching the database**, so the loader is nothing but I/O and the write path is never waiting on computation.

## 4.2 Loader pattern

```cypher
UNWIND $rows AS row
CREATE (p:Person {id: row.id, handle: row.handle, role_rank: row.role_rank, team: row.team})
```

```cypher
UNWIND $rows AS row
MATCH (a:Person {id: row.src})
MATCH (b:Person {id: row.dst})
CREATE (a)-[:COMMUNICATES {weight: row.w, first_epoch: row.f, last_epoch: row.l}]->(b)
```

**Load order matters** — all nodes before any edges, since `MATCH` on both endpoints must succeed.

## 4.3 Day-one throughput measurement — DO THIS FIRST

Before designing anything at final scale, measure real throughput:

1. Bring up the node against local MinIO with `RUST_MIN_STACK=33554432` set.
2. `UNWIND` batch-insert 10,000 edges at batch sizes **500 / 1,000 / 2,000 / 5,000**.
3. Record wall-clock per batch size; compute edges/sec at the best one.
4. Multiply by **6 usable ingest-hours**. That is your ceiling.
5. **Target 50% of that.**

Record the result in the README as a measured engineering finding. It demonstrates you understood the architecture, and it keeps scope honest.

If throughput is catastrophically low, cut in this order: drop `ABOUT` edges for artifacts older than a cutoff → drop artifacts of kind 5 (docs) → restrict to a subset of products.

---

# PART 5 — THE THREE ANALYSES

## 5.1 GHOST — the shadow org chart

**Goal:** rank people by how much of the organization's communication actually routes through them, then contrast that with their formal rank.

**Method: sampled betweenness.** The engine has no global betweenness, so approximate it — this is a standard, defensible approach (Brandes-style sampling), and you should name it as such in the README rather than implying exact centrality.

**Algorithm:**

1. Select K source persons and K target persons (K ≈ 150–200; use all 530 if throughput allows, in batches).
2. Run one batched pairwise query:

```cypher
CALL algo.MSpaths({
  sourceLabel: 'Person', sourceProperty: 'id', sourceValues: $sources,
  targetLabel: 'Person', targetProperty: 'id', targetValues: $targets,
  relTypes: ['COMMUNICATES'], relDirection: 'BOTH',
  maxLen: 4, pairwise: true, pathCount: 3
}) YIELD path, pathCost
RETURN collect(path) AS paths
```

3. Client-side: for every returned path, tally each **intermediate** node (exclude endpoints). Divide by the number of source-target pairs sampled.
4. Rank descending. This is the shadow centrality score.

**The reveal:** join the ranking against `role_rank`. Compute `structural_rank - formal_rank`. The person with the largest positive gap is the story — the individual contributor whose structural position vastly exceeds their title.

**Also compute the bus-factor claim:** for the top-ranked person, re-run the sampled query with that person's edges excluded (simplest implementation: exclude any path containing them, client-side) and report how many source-target pairs become unreachable within `maxLen`. State it precisely: *"N of M sampled pairs have no communication path within 4 hops without this person."* Do not say "the company stops."

## 5.2 FAULTLINE — dependency without communication

**Goal:** find module pairs that technically depend on each other whose owners have no communication path.

**Algorithm:**

1. Enumerate dependent module pairs:

```cypher
MATCH (m1:Module)-[d:DEPENDS_ON]->(m2:Module)
RETURN m1.id, m2.id, d.weight
```

2. For each pair, resolve owners:

```cypher
MATCH (p:Person)-[o:OWNS]->(m:Module)
WHERE m.id = $moduleId AND o.confidence > 50
RETURN p.id, o.confidence
```

3. Batch all owner pairs into a single pairwise reachability test:

```cypher
CALL algo.MSpaths({
  sourceLabel: 'Person', sourceProperty: 'id', sourceValues: $ownersA,
  targetLabel: 'Person', targetProperty: 'id', targetValues: $ownersB,
  relTypes: ['COMMUNICATES'], relDirection: 'BOTH',
  maxLen: 4, pairwise: true, pathCount: 1
}) YIELD path
RETURN collect(path) AS reachable_pairs
```

4. **Any owner pair with no returned path is a faultline.** Severity = `DEPENDS_ON.weight` (how much they technically interact) with no communication path present.

5. Also emit a "weak coordination" tier: pairs that *are* connected but only at path length 3–4, meaning they communicate solely through intermediaries.

**Output:** a ranked table — module A, module B, dependency weight, owner A, owner B, communication path length (or "none").

**If you have any defect or incident signal** in the dataset (bug tickets, incident artifacts), overlay it: what fraction of incidents touch modules flagged as faultlines, versus base rate? **Report this honestly, including if the answer is "no lift."** A null result reported cleanly is more credible than a hedged positive.

## 5.3 SPOLIATION — the missing record

**Goal:** identify records that structurally must have existed and are absent.

**Three detection rules, applied during ingest:**

1. **Dangling thread parent.** An artifact `REPLIES_TO` an id with no corresponding artifact in the corpus. → Create `Phantom` with `reason: 1`.
2. **Sequence gap.** A thread contains `thread_seq` values 1, 2, 4, 5. Position 3 is missing. → Create `Phantom` with `reason: 2`, `inferred_epoch` interpolated between neighbours.
3. **Unexplained state transition.** A ticket moves from one state to another with no intervening artifact recording why. → Create `Phantom` with `reason: 3`.

**The query that makes it a graph finding** — a chain of custody that routes *through* an absent record:

```cypher
CALL algo.SPpaths({
  sourceNode: $executiveArtifactId,
  targetNode: $codeChangeArtifactId,
  relTypes: ['REPLIES_TO', 'EXPECTED_BEFORE'],
  relDirection: 'OUTGOING',
  maxLen: 8, pathCount: 5
}) YIELD path, pathCost
RETURN path, pathCost
```

A path that traverses a `Phantom` node is a structural proof that **the chain existed and a link is missing.** That is the finding: not "we can't find the record," but "the graph requires a record here and it is absent."

**State the limitation plainly in the UI and README:** absence in the corpus is not proof of deletion. It is proof that the corpus is structurally incomplete at that point. Judges reward stated limitations far more than they punish them.

---

# PART 6 — EVALUATION

Three separate results. Report all three, including negatives.

## 6.1 Against HERB (the headline number)

Run HERB's question set through a retrieval path that uses the graph:
- For each question, resolve entities to integer ids
- Gather the relevant subgraph via `algo.MSpaths`
- Feed the resolved subgraph to a reader model
- **Abstain when no path exists** — roughly half of HERB's queries are unanswerable, so this is worth disproportionate points

**Report:** overall score vs the published **32.96**, plus answerable/unanswerable split, plus correct-abstention rate.

**Baseline to build yourself:** a vector or keyword RAG over the same corpus. You need the contrast on screen.

## 6.2 Ghost validation

There is no ground-truth "real org chart." Convince a skeptic differently:
- Show the ranking is **stable** across independent samples (re-run with different K-samples; top-10 should be largely consistent)
- Show it **differs materially** from naive degree centrality — if it just reproduces "who talks the most," it isn't interesting
- Report the removal experiment precisely (§5.1)

## 6.3 Faultline validation

- Precision/recall of flagged module pairs against any incident/bug signal in the corpus
- **Baseline:** churn × complexity hotspots (this is what CodeScene-style tools use)
- **If there is no lift over baseline, say so.** Then reframe as coordination debt and move the demo's weight to Ghost.

---

# PART 7 — THE PRODUCT

## 7.1 UI

A single-page app, three panels, one graph.

**Panel 1 — The Org.** Force-directed graph of `Person` nodes sized by shadow centrality, coloured by team. A toggle switches between "Official" (sized by `role_rank`) and "Actual" (sized by computed centrality). The switch is the demo's centrepiece — nodes visibly resize.

**Panel 2 — Faultlines.** The module dependency graph overlaid with communication edges. Dependency edges with no communication path underneath render **red and pulsing**. Sortable table beside it: module A, module B, weight, owners, comm distance.

**Panel 3 — Gaps.** Chain-of-custody view. Enter two artifacts, render the path, and highlight any `Phantom` node in the chain with the inferred timestamp and the detection reason.

**Every panel must show the Cypher query that produced it.** A judge assessing "use of HydraDB" needs to see the engine working, not infer it.

## 7.2 Setup — ship your own one-command install

There is no official one-command setup for the engine. **Build one.** A `docker-compose.yml` bringing up `graph-node` + MinIO + the loader + seed data, plus a `./setup.sh`, targeting **under 60 seconds to a live UI**.

This directly serves "product completeness and usability" and the pre-submission checklist item "setup instructions actually work." Most entries will not do this.

## 7.3 Demo video — ≤3:00, hard stop

Order is specified by the organizers: problem → project → demo → HydraDB.

| Time | Content |
|---|---|
| 0:00–0:25 | **Problem.** "Every company has an org chart. It's fiction. The real structure is buried in who actually talks to whom — and nobody has ever drawn it." |
| 0:25–0:40 | **What we built.** X-Ray, on self-hosted open-source HydraDB. One command. |
| 0:40–1:10 | **MONEY SHOT.** Official org chart on screen. Click "Actual." Nodes resize — and a mid-level engineer becomes the largest node on the screen. *"Every critical path in this company routes through her. She reports two levels below the person everyone thinks runs this."* |
| 1:10–1:45 | **Faultlines.** Overlay the code graph. One thick dependency edge pulses red with no communication edge beneath it. *"These two modules interact constantly. Their owners have never exchanged a message."* Cut to the incident that later landed there — if the data supports it. |
| 1:45–2:10 | **The gap.** Chain of custody from a directive to a code change. A phantom node flashes mid-chain. *"The graph requires a record here. It isn't in the corpus."* |
| 2:10–2:45 | **Why HydraDB.** `algo.MSpaths` pairwise, bounded traversal, GraphBLAS, snapshot reads. *"Sampled betweenness across 200×200 people is one server-side call. Without it this is 40,000 round trips."* Show the query. |
| 2:45–3:00 | **Results.** HERB score vs 32.96. Repo link. Stop. |

Run against local MinIO with a warm cache. Rehearse the exact click path. **Nothing past 3:00 will be reviewed.**

## 7.4 README — required sections

1. **What this is** — one paragraph
2. **The thesis** — the two-graphs insight, in plain language
3. **Setup** — copy-pasteable, including `export RUST_MIN_STACK=33554432`, `just` recipes, and the **pinned HydraDB commit hash**
4. **How HydraDB is used** — the section that wins criterion #2. Answer three things in order:
   - Which primitives, and where: `algo.MSpaths` pairwise for sampled betweenness and for faultline reachability; `algo.SPpaths` for chain-of-custody; bounded traversal throughout
   - What breaks without it: sampled betweenness becomes 40,000 client round trips; the faultline test becomes an N² query storm
   - Why a vector index categorically cannot do this: the signal is the **absence of an edge in one graph where a corresponding edge exists in another**. That is a two-graph structural comparison. A vector index has one embedding space and no concept of "edge present here but not there."
5. **Measured throughput** — your day-one ingest numbers
6. **Scale and limitations** — subset size, `maxLen` bounds, the sampling approximation, the fact that corpus absence ≠ deletion
7. **Evaluation** — all three results, negatives included
8. **Attribution** — datasets, libraries, LLM APIs, AI coding assistants
9. **License** — an OSI-approved LICENSE file in the repo root

---

# PART 8 — SCHEDULE

Deadline: **20 August 2026, 11:59 PM PT** = **21 August, 12:29 PM IST**.

| Day | Deliverable |
|---|---|
| **Day 1** | Node running on local MinIO with `RUST_MIN_STACK`. Cypher round-trip. **Throughput measurement (§4.3).** Fresh public repo with license, first commit today. Pin the engine commit. HERB downloaded and inspected. |
| **Day 2** | Schema frozen. Extraction pipeline running. `Person` + `Artifact` + `AUTHORED` + `REPLIES_TO` loaded. **Milestone: one `algo.MSpaths` call returns real paths.** |
| **Day 3** | `COMMUNICATES`, `OWNS`, `DEPENDS_ON`, `Phantom` derived and loaded. **Milestone: Ghost ranking produces a plausible top-10.** |
| **Day 4** | Faultline detection working. Spoliation chain query working. **Milestone: all three analyses produce output.** |
| **Day 5** | UI, three panels, query display. HERB eval harness running. Baseline built. |
| **Day 6** | **HARD FEATURE FREEZE, end of day.** Numbers locked. README written. Anything not demoable is cut. |
| **Day 7** | Docker compose + `setup.sh`. Clean-clone test on a different machine. Record video twice. |
| **Day 8** | Polish, edit, **submit early**. Verify every link in an incognito window. |
| **Day 9** | Buffer only. Re-verify. Do not start anything new. |

---

# PART 9 — FAILURE MODES

| Risk | Mitigation |
|---|---|
| **Faultline shows no predictive lift** | Expected as a real possibility. Reframe to "coordination debt," shift demo weight to Ghost. **Report the null result honestly** — it is more credible than a hedged positive. |
| Ingest overruns | Measure day one. Cut in the order given in §4.3. The core graph is small by design. |
| Cold-storage latency in the demo | Local MinIO, pre-warmed cache, rehearsed click path. Never real S3. |
| Hitting unsupported Cypher | `cypher-compat.md` open at all times. Name→int dictionary from hour one. Bound every path. |
| `RUST_MIN_STACK` unset → node aborts | Put it in the setup script *and* the README. |
| Sampled betweenness unstable | Increase K; report stability across samples as part of the evaluation. |
| Owner attribution wrong | Use a confidence threshold; show confidence in the UI; validate a hand-labelled sample of 20. |
| Phantom false positives | Three independent detection rules; report each separately with counts; state that absence ≠ deletion. |
| Judges can't reproduce | Ship compose + `setup.sh`; test from a clean clone on a machine that isn't yours. |
| "Where is HydraDB doing the work?" | Show the queries in the UI. State the round-trip argument explicitly. |

---

# PART 10 — DEFINITION OF DONE

- [ ] Public GitHub repo, OSI license, **no commits before the build window opened**
- [ ] `./setup.sh` brings up a working system from a clean clone in under 60 seconds
- [ ] All three analyses produce output on the real HERB corpus
- [ ] HERB evaluation run, scored, compared against 32.96 and a self-built baseline
- [ ] UI shows all three panels **and the Cypher behind each**
- [ ] Video ≤ 3:00, correct order, money shot before 1:10
- [ ] README contains all nine sections from §7.4, including measured throughput and stated limitations
- [ ] Pinned engine commit recorded
- [ ] Submitted before the deadline with every link verified in an incognito window

---

# PART 11 — ANTI-GOALS

**Do not:**
- Use the hosted product at `api.hydradb.com`, its SDKs, or any of its features. It is a different system and is not judged.
- Put fuzzy matching, embeddings, or similarity anywhere in the query path. All resolution happens offline in the loader.
- Use `IN`, `CONTAINS`, `min()`, `max()`, `RETURN *`, unbounded `*` paths, or multi-typed variable-length patterns. They will not parse.
- Match nodes on strings. Integer ids only.
- Build entity resolution as the headline feature. That is what every other Track 01 entry is doing.
- Claim exact betweenness. Say sampled, and cite the approximation.
- Claim proof of deletion. Say the corpus is structurally incomplete at that point.
- Load all 500,000 EnterpriseRAG-Bench documents. Use HERB.
- Add a fourth analysis. Three lenses, then freeze.
