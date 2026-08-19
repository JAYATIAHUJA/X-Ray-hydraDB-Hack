<div align="center">

# X-Ray Evidence Platform

**Ask who owns, authored, or reviewed work — then inspect coordination structure around the answer.**<br>
**X-Ray pairs typed ontology traversal with structural/formal rank and evidence-backed what-if analysis.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://python.org)
[![Node](https://img.shields.io/badge/node-22+-green.svg)](https://nodejs.org)
[![HydraDB](https://img.shields.io/badge/HydraDB-pinned%20%2302a40025-blueviolet.svg)](infra/runtime-images.lock)
[![HackHydra 2026](https://img.shields.io/badge/HackHydra%202026-Track%2001-orange.svg)](https://hackhydra.hydradb.com)

</div>

<p align="center">
<b>Official Track 01 corpus (HERB, all 30 products): 5,126 people · 5,615 communication edges · Ghost #1 is a Software Engineer ranked #282 on paper</b><br/>
<sub>Same ranking with every unresolved handle removed (top-10 overlap 1.0). Plus Apache Kafka (real, 292 people) and a 500-person synthetic org with planted ground truth. Every number traces to a results file stamped with the engine digest. Full graph incl. artifacts: 46k nodes / 92k edges — the analysed graph is the people.</sub>
</p>

---

## What is X-Ray?

X-Ray reads your engineering organization's offline exports — Slack, email, JIRA, Confluence, GitHub Issues, git — and builds two graphs:

- **The human graph** — who replies to whom, across every channel
- **The work graph** — which modules depend on which, from git co-changes and tickets

The query surface answers ownership, authorship, and review questions over typed edges with evidence IDs. The analysis surface then compares structural rank with formal rank, tests bounded removal impact, and finds missing coordination or record edges. Betweenness itself is standard; the product is the pairing and traceability.

> **A vector database retrieves similar text. X-Ray asks: is there a communication path of length ≤ 4 between the owners of two co-changing modules?** That question requires typed graph traversal — HydraDB's `algo.MSpaths` — not similarity search.

---

## Three lenses. One question each.

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   👻 GHOST          ⚡ FAULTLINES         🕳 GAPS                   │
│                                                                     │
│   Who is quietly    Where does work      Where is a required        │
│   load-bearing?     depend on work       evidence step              │
│                     with no human        absent from                │
│   Structural rank   coordination path    the corpus?                │
│   vs formal rank    between owners?                                 │
│                                          Phantom nodes mark         │
│   Bus-factor:       Shortest bridge      the missing steps          │
│   pairs lost if     suggestion           in the chain               │
│   removed           included                                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

Every finding includes: source evidence IDs · confidence score · content SHA-256 · executed HydraDB query · one recommended action.

---

## Results at a glance

### Salesforce HERB — the official Track 01 corpus (all 30 products)

HERB ships explicit employee ids, a role hierarchy, Slack with `@eid` mentions, and pull requests with reviewers. X-Ray reads exactly those ids — nothing is inferred from prose — through the same pipeline as every other source ([adapter](packages/xray_ingest/src/xray_ingest/adapters/herb.py) · [builder](scripts/build_herb_corpus.py)).

| Finding | Result |
|---|---|
| **Analysed graph** | **5,126 people · 5,615 COMMUNICATES edges** (from 4,609 review replies + explicit `@eid` mentions). Full graph incl. artifacts: 46,073 nodes / 92,148 edges |
| **Ghost #1** | Emma Jones, *Software Engineer* — structural rank **#1**, formal rank **#282** (+281) |
| **Ghost top-10** | 4 of 10 are ICs (role 1); largest gap in top-10: Ian Miller, structural #10 vs formal **#461** |
| **Bounded removal impact** | Remove structural #1 → 75 of 23,870 reachable pairs lose their ≤4-hop path (**0.314%**); reported as a small effect, not a bus-factor claim |
| **Identity robustness** | Drop all 4,596 unresolved handles and re-rank the 530 named employees: **top-10 overlap 1.0, same #1**. The ranking is not an artefact of anonymous ids padding the graph |
| **Faultlines** | **0 — a null result, reported as such.** HERB PRs are single-product; no cross-product co-change exists in the corpus, so no `DEPENDS_ON` edge is derived and none is invented |
| **Phantom gaps** | 0 — every review reply resolves to its PR artifact; HERB Slack has no thread metadata, so no dangling parents are claimed |
| **Identity** | 530 employees resolve by `eid`; 4,596 PR logins (`EMP_…`) have no HERB mapping and stay **visibly unresolved** (a stated limitation, not a merge) |
| **Execution** | HydraDB runs one bounded multi-source path operation; the checked-in client timing is a same-question Python baseline, not a claim that production clients issue millions of network requests |

Two "Emma Jones" and two "Ian Miller" appear in the top-10 — HERB deliberately reuses names. X-Ray keeps them separate because identity is the explicit `eid`, not the display name; that is the entity-resolution trap the track description warns about, handled by design.

Reproduce: `uv run python scripts/build_herb_corpus.py --all --out data/snapshots/herb-2026 && uv run python scripts/eval_corpus.py --snapshot data/snapshots/herb-2026 --json docs/results/herb-2026.json`

### Apache Kafka — real public corpus (Mar–Jun 2025)

| Finding | Result |
|---|---|
| **Ghost #1** | Chia-Ping Tsai (PMC) — structural rank #1, formal rank #4 |
| **Largest rank gap** | PoAn Yang, committer — structural #5 vs formal #34 **(+29)** |
| **Bounded removal impact** | Remove structural #1 → 516 of 6,295 reachable pairs lose their ≤4-hop path (**8.197%**) |
| **Faultlines found** | 49 — top: `clients ↔ connect`, co-changed 9×, no reply path between owners |
| **Phantom gaps** | 135 dangling thread parents — **53 inside the export window** (reply ≥30 days in, parent still absent from the corpus) · 82 at the export boundary (parent most likely predates the export; reported, not counted as a finding) |
| **Identity robustness** | Drop the 12 unresolved handles → top-10 overlap 0.9, same #1 |
| **Execution** | One HydraDB multi-source path operation; compare engine and local timings in `docs/results/latency.json` |

### Synthetic 500-person org — ground truth evaluation

| Metric | Value |
|---|---|
| Faultline precision / recall | **1.000 / 1.000** (3 planted, 3 found, 0 false positives) |
| Gap precision / recall | **1.000 / 1.000** (5 planted, 5 found) |
| Ghost top-10 overlap vs exact betweenness | **0.933** |
| What-if: remove the planted Ghost | 110,883 of 124,251 pairs lose their ≤4-hop path |
| Execution | One bounded multi-source path operation, with a local reference implementation used for validation |

Sources: [docs/results/herb-2026.json](docs/results/herb-2026.json) · [docs/results/kafka-2025q2.json](docs/results/kafka-2025q2.json) · [docs/results/synth500.json](docs/results/synth500.json)

---

## Architecture

### Ingest pipeline

```
  Slack Export JSON          ┐
  Email (.mbox)              │   ┌─────────────────────────────────┐
  JIRA CSV                   ├──▶│   Source adapters               │
  Confluence XML             │   │   (explicit IDs only — no NLP)  │
  GitHub Issues CSV          │   └──────────────┬──────────────────┘
  Git log                    ┘                  │
                                                ▼
                                   ┌────────────────────────┐
                                   │  Identity resolution    │
                                   │  identity.json          │
                                   │  alice@co.com  → alice  │
                                   │  U0123ABC      → alice  │
                                   │  alice_jira    → alice  │
                                   └──────────┬─────────────┘
                                              │
                                              ▼
                               ┌──────────────────────────────┐
                               │  Canonical pipeline          │
                               │  canonicalize                │
                               │     → derive_edges           │
                               │     → detect_gaps            │
                               └──────────────┬───────────────┘
                                              │
                                              ▼
                               ┌──────────────────────────────┐
                               │  HydraDB  (bolt://)          │
                               │  UNWIND batch loader         │
                               │  500 edges/batch · ~4,300/s  │
                               └──────────────┬───────────────┘
                                              │
                          ┌───────────────────┼───────────────────┐
                          ▼                   ▼                   ▼
                    algo.MSpaths       algo.MSpaths        algo.SPpaths
                    Ghost scoring      Faultline           Gap chain
                    (bounded ≤4)       reachability        of custody
```

### Graph schema

```
  person:alice ──COMMUNICATES──▶ person:bob
       │                              │
     OWNS                           OWNS
       │                              │
       ▼                              ▼
  module:payments-api ──DEPENDS_ON──▶ module:ledger
       │
     ABOUT
       │
       ▼
  artifact:commit:abc123 ──REPLIES_TO──▶ artifact:ticket:JIRA-456
                                              │
                                        PRECEDED_BY
                                              │
                                              ▼
                                   artifact:Phantom (missing approval)
```

### API + live/fallback pattern

```
  React UI
     │
     │ fetch /api/v1/snapshots/{id}/ghosts
     ▼
  FastAPI
     │
     ├─── XRAY_HYDRA_URI set? ──YES──▶ HydraDB query (algo.MSpaths)
     │                                   └─ returns: result + query text
     │                                              + engine_ms + round_trips
     │
     └──────────────────NO──▶ in-process bounded BFS fallback
                               └─ header shows "fallback" · never pretends live
```

---

## Enterprise ontology

X-Ray's type system is intentionally small — five node types, eight relationship types. Every node has a deterministic 63-bit BLAKE2b ID and every edge retains its source evidence.

### Node types

| Type | Meaning | Example key |
|---|---|---|
| `Person` | Named individual in the corpus | `person:alice` |
| `Team` | Org unit from directory export | `team:platform` |
| `Artifact` | A discrete communication or work output | `artifact:email:msg-1234` |
| `Module` | Logical code or document scope | `module:payments-api` |
| `Phantom` | Structurally required but absent record | `artifact:missing-approval` |

### Relationship types

| Relationship | Direction | Derived from |
|---|---|---|
| `COMMUNICATES` | Person → Person | email reply, Slack thread reply, mention |
| `OWNS` | Person → Module | authorship density in git; explicit ownership |
| `DEPENDS_ON` | Module → Module | co-change in commits, `Depends-On:` trailers, Confluence links |
| `AUTHORED` | Person → Artifact | email From, git author, Slack user, ticket reporter |
| `ABOUT` | Artifact → Module | explicit module reference in export |
| `REPLIES_TO` | Artifact → Artifact | `In-Reply-To` header, Slack `thread_ts`, Confluence comment → page |
| `PRECEDED_BY` | Artifact → Artifact | sequence contract: step B must follow step A |
| `REPORTS_TO` | Person → Person | `manager_external_id` in directory record |

> A vector database retrieves documents similar to a query. It cannot express: *"is there a `COMMUNICATES` path of length ≤ 4 between the `Person` nodes who most recently `AUTHORED` changes to two `DEPENDS_ON`-linked `Module` nodes?"* That requires typed graph traversal with bounded hop counts.

---

## Entity resolution

X-Ray resolves all identities **before** graph ingestion — never inside the engine.

```
  Raw source IDs                     Canonical handle
  ─────────────────────────────────────────────────────
  alice@company.com          ─┐
  U0123ABC   (Slack)          ├──▶  person:alice   (one node, one integer ID)
  alice       (GitHub)        │
  alice_jira  (JIRA)          ┘

  unknown@vendor.com         ──▶  unresolved-a3f7c2  (visible, flagged in UI)
```

**How the identity map works:**

```json
{
  "alice@company.com": "alice",
  "U0123ABC":          "alice",
  "alice":             "alice",
  "alice_jira":        "alice"
}
```

- IDs not in the map become visible `unresolved-<hash>` handles — no silent merging
- The limitation is surfaced in the UI and the risk report
- Once resolved, a canonical handle maps to a **stable 63-bit BLAKE2b integer** — the graph is bit-for-bit reproducible across runs
- Resolving inside the engine (e.g. email-domain fuzzy matching) risks merging distinct people or splitting one person; X-Ray treats this as a pre-ingestion step so the graph contains only explicit facts

---

## Supported sources (7 adapters)

| Source | Adapter | Key fields |
|---|---|---|
| Slack export JSON | `slack_export_rows` | `id`, `occurred_at_epoch`, `author_id`, `parent_ts` |
| Email (`.mbox`) | `mbox_rows` | `id`, `occurred_at_epoch`, `from_id`, `to_ids`, `In-Reply-To` |
| JIRA CSV | `jira_csv_rows` | `id`, `occurred_at_epoch`, `reporter_id`, `module_keys` |
| Confluence XML | `confluence_xml_rows` | `id`, `occurred_at_epoch`, `reporter_id`, `space→module_keys` |
| GitHub Issues CSV | `github_csv_rows` | `id`, `occurred_at_epoch`, `reporter_id`, `label→module_keys` |
| Git log | `git_log_rows` | `sha`, `occurred_at_epoch`, `author_id`, `Depends-On:` trailers |
| Salesforce HERB (Track 01 corpus) | `herb_slack_rows` · `herb_pr_rows` · `herb_document_rows` · `herb_directory_records` | `eid` authors, `@eid` mentions, PR `user`/`reviews`, `employee.json` roles → `role_rank` |

All adapters: **explicit IDs only** — no NLP, no guessing module assignments from message text.

---

## How HydraDB is used

| Operation | HydraDB query | What it replaces |
|---|---|---|
| Structural scoring | one pairwise `algo.MSpaths` over the explicitly undirected coordination projection | the same bounded-path calculation in the local reference implementation; both timings are reported on the same machine when benchmarked |
| Faultline reachability | one bounded `algo.MSpaths` per candidate pair | unbounded client traversal loop |
| Gap chain | `algo.SPpaths` over `PRECEDED_BY` | multi-hop manual BFS |
| Graph load | `UNWIND` batch writes · 500 edges/batch | row-by-row inserts |

The API exposes the **exact executed query**, parameters, max length, round trips, and engine time on every lens response. The UI shows it in a query card next to each result.

```
HydraDB query card (shown live in UI):
┌──────────────────────────────────────────────────────────────────┐
│ CALL algo.MSpaths({                                              │
│   start_nodes: [42, 91, 134],                                    │
│   end_nodes:   [42, 91, 134],                                    │
│   rel_types:   ["COMMUNICATES"],                                 │
│   max_len:     4,                                                │
│   path_key:    "path_key"                                        │
│ })                                                               │
│                                                                  │
│ engine: 12 ms  ·  round trips: 1  ·  source: hydradb            │
│ replaces: 6,295 per-pair calls  ·  speedup: ≥ 42×               │
└──────────────────────────────────────────────────────────────────┘
```

---

## Quick start

### Open a shipped corpus with one click

The dashboard's **Load data** screen lists every bundled corpus (demo, synth-500, Kafka, HERB once built) — pick one and it is served immediately (`POST /api/v1/snapshots/activate`, restricted to `data/snapshots/*` and bundled fixtures). Your own exports remain the second path on the same screen.

### Hosted-style demo (web + API, no engine required)

```bash
docker compose -f compose.demo.yaml up --build
# http://localhost:8080  →  landing · http://localhost:8080/app  →  dashboard on the Kafka snapshot
```

Deploy the same two images anywhere Docker runs — Fly configs and notes in [infra/deploy](infra/deploy/README.md).

### One-command local stack

```sh
# macOS / Linux
./scripts/setup.sh

# Windows PowerShell
scripts\setup.ps1
```

Starts HydraDB + MinIO (Docker), syncs Python deps, seeds fixture, starts API + web UI. Expected result: browser opens, header shows **HydraDB: live**.

### Development mode (macOS/Linux)

```bash
# Terminal 1 — API
uv sync
export PYTHONPATH="apps/api/src:packages/xray_analytics/src:packages/xray_core/src:packages/xray_hydra/src:packages/xray_ingest/src:packages/xray_runtime/src"
uv run uvicorn xray_api.app:app --reload

# Terminal 2 — Web
npm install
export VITE_XRAY_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```

Without `XRAY_HYDRA_URI`, the API stays in **fixture fallback mode** — the health endpoint reports `fallback` and every lens result is labelled accordingly. Nothing pretends to be live.

### Configure HydraDB

```powershell
$env:XRAY_HYDRA_URI      = "bolt://localhost:7687"
$env:XRAY_HYDRA_USER     = "neo4j"
$env:XRAY_HYDRA_PASSWORD = "password"
$env:XRAY_HYDRA_DATABASE = "neo4j"

# Seed the bundled demo fixture
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/hydra/seed-fixture
```

Pinned container and MinIO topology: [infra/runtime-images.lock](infra/runtime-images.lock) · [compose.yaml](compose.yaml)  
Current HydraDB source commit: `02a40025d2d57e97ab2754c8256219cdbfeab379`  
Required env: `RUST_MIN_STACK=33554432` (already set in compose).

### Bring your own exports

```powershell
git log --name-only --format="%x1e%H%x1f%at%x1f%ae%x1f%s%x1f%b" > git.log

uv run python scripts/ingest_export.py `
  --dataset-id   my-team `
  --directory    directory.json `     # people / teams / modules
  --identity-map identity.json `      # {"alice@co.com": "alice", "U0123": "alice"}
  --mbox         dev.mbox `           # mailing list export
  --jira-csv     jira.csv `
  --confluence-xml entities.xml `     # Confluence Space Export
  --github-csv   issues.csv `         # gh issue list --json > issues.csv
  --git-log      git.log `
  --module-prefixes modules.json `    # {"services/payments": "payments-api"}
  --slack-dir    slack-export/ `
  --out          data/snapshots/my-team
```

---

## Shipped corpora

| Corpus | People | Edges | How to run |
|---|---|---|---|
| `xray-demo` | 10 synthetic | 47 | default — runs with no config |
| `xray-synth-500` | 500 synthetic + planted ground truth | 1,319 | `XRAY_FIXTURE_VARIANT=synth500` |
| `kafka-2025q2` | 292 real (Apache Kafka) | 4,476 | `XRAY_SNAPSHOT_DIR=data/snapshots/kafka-2025q2` |
| `herb-2026` | 5,126 (official Track 01 corpus, 30 products) | 92,148 | `scripts/build_herb_corpus.py --all` then `XRAY_SNAPSHOT_DIR=data/snapshots/herb-2026` |

```powershell
# Run the Kafka corpus
$env:XRAY_SNAPSHOT_DIR = "data/snapshots/kafka-2025q2"
uv run uvicorn xray_api.app:app --reload
```

---

## Local ingest measurement

Measured on one local HydraDB + MinIO setup, 16 Aug 2026. Node setup excluded from timing. This is capacity-planning data for this loader, not a cross-database benchmark; no Neo4j performance claim is made.

```powershell
uv run python scripts/bench_ingest.py --edges 10000 --people 500
```

| Batch size | Edges | Time | Edges / sec |
|---:|---:|---:|---:|
| 500 | 10,000 | 2.302 s | **4,344** |
| 1,000 | 10,000 | 2.460 s | 4,065 |
| 2,000 | 10,000 | — | admission control limit |

Default batch size: 500. This runtime rejects queries above 1,024 items.

Full benchmark data: [docs/results/latency.json](docs/results/latency.json) · [docs/results/throughput.json](docs/results/throughput.json)

---

## Evaluation

### Synthetic org (reproducible)

```powershell
uv run python scripts/eval_synth.py --json docs/results/synth500.json
```

| Metric | Value |
|---|---:|
| Faultline precision | **1.000** |
| Faultline recall | **1.000** |
| Faultlines planted / returned | 3 / 3 |
| Gap precision | **1.000** |
| Gap recall | **1.000** |
| Gaps planted / returned | 5 / 5 |
| Ghost top-1 hit rate | **1.000** |
| Ghost mean top-10 overlap vs exact betweenness | **0.933** |
| What-if: remove the planted Ghost | 110,883 of 124,251 reachable pairs lose ≤4-hop path |

The planted Ghost is **Priya Nair** — structural rank #1, formal rank #33 (gap +32). She does not head the reporting chain. That is the point of the lens.

The fixture includes a **negative control**: four coordinated dependencies whose owners communicate directly. They must not be flagged. They are not.

### Apache Kafka (real corpus)

Identity resolved offline by exact ASF id / email / case-folded public name joins only.

| Metric | Value |
|---|---:|
| People / modules / artifacts / phantoms | 292 / 26 / 1,841 / 135 |
| Sources | 850 emails · 397 tickets · 597 commits |
| Ghost #1 | Chia-Ping Tsai (PMC) — structural #1, formal #4 |
| Largest rank gap | PoAn Yang — structural #5, formal #34 **(+29)** |
| Faultlines | 49 — top: `clients ↔ connect`, co-changed 9×, no reply path |
| Incident lift | **not measurable** — corpus has no module-linked incident signal |
| Engine leverage | 1 `algo.MSpaths` call replaces **42,486** per-pair queries |

> **Honest note:** An earlier build split `jsancio` into two handles and reported a `core ↔ metadata` faultline between them. Merging on the exact ASF id removed it — because those two people talk to each other. Faultline output is only as good as the identity map. That is why unresolved IDs are surfaced rather than hidden.

---

## Verification

```powershell
uv run pytest                           # 13 contract tests
uv run mypy                             # type checking
npm --prefix apps/web run typecheck     # TypeScript
npm --prefix apps/web test              # Vitest
npm --prefix apps/web run lint
npm --prefix apps/web run build
```

Clean-clone judge script (runs all of the above from scratch):

```sh
./scripts/verify_clean_clone.sh
```

Oracle test — bounded BFS vs networkx ground truth:

```powershell
uv run pytest tests/contract/test_oracle.py -v
```

---

## Honest limitations

X-Ray reports negative results as plainly as positive ones:

- **Betweenness is not new** (Freeman 1977). Corpora below 2,000 people use exact NetworkX betweenness; larger corpora disclose bounded Brandes or HydraDB MSpaths as the calculation method. The contribution is structural rank × formal rank × what-if removal × evidence, not the metric.
- A **Faultline** is coordination debt, not a predicted incident. The socio-technical-congruence literature is contested (Cataldo 2009 for; Mauerer 2021 against), so no causal claim is made — and on HERB the lens returns **0**, because the corpus has no cross-module signal. It says so instead of padding.
- A **Phantom** (Gap) marks structural incompleteness, never automatic evidence of deletion. Each one is labelled `in_window` (parent should be in this export and is not) or `export_boundary` (reply falls in the first 30 days; parent probably predates the export). Only the former is worth a question; both are reported.
- **Identity resolution is deliberately conservative**: explicit ids only. On HERB, 4,596 PR logins have no employee mapping and stay visibly unresolved; the Ghost top-10 is unchanged when they are removed. Unresolved counts and names are surfaced in every response, never merged by guesswork.
- Measured corpora are one labelled synthetic org and one public open-source project. Neither is a claim about a private company.
- Live OAuth connectors are intentionally out of scope. Export adapters are the supported ingest path.
- `maxLen=4` remains the live HydraDB product bound. Run `uv run python scripts/eval_max_len.py --snapshot PATH --json docs/results/maxlen.json` to disclose top-k stability over bounds 2–6 on any real snapshot.

### Privacy and appropriate use

X-Ray is a team-coordination aid, not an employee performance or termination system. Deployments should use role-based access, short retention windows, aggregate views by default, and corpora collected with appropriate notice and authorization. Reply asymmetry and structural rank require team context; neither is a measure of individual value or intent. Evidence hashes establish record integrity, not permission to use workforce data for unrelated decisions.

---

## Project structure

```
hydra/
├── apps/
│   ├── api/          # FastAPI — three lenses + import + risk report
│   └── web/          # React + TanStack Query + Cytoscape.js
├── packages/
│   ├── xray_analytics/   # Ghost, Faultline, Gap algorithms + shortest bridge
│   ├── xray_core/        # Canonical models, evidence, CanonicalBundle
│   ├── xray_hydra/       # HydraDB gateway, loader (batch + checkpoint), health
│   ├── xray_ingest/      # 6 source adapters + canonicalize pipeline
│   └── xray_runtime/     # In-process fixture fallback
├── tests/contract/   # Oracle tests, loader crash-resume, adapter contracts
├── scripts/          # demo.sh, demo.ps1, verify_clean_clone.sh, bench_*
├── docs/results/     # Checked-in JSON — every table above traces here
├── data/snapshots/   # kafka-2025q2 snapshot ships in the repo
└── infra/            # compose.yaml, runtime-images.lock (pinned HydraDB)
```

---

## Attribution

- [HydraDB](https://github.com/hydra-db/hydradb) — graph database runtime
- Built for **HackHydra 2026 Track 01** by [Jayati Ahuja](https://github.com/JAYATIAHUJA)

## License

Apache License 2.0 — see [LICENSE](LICENSE).  
Third-party components, AGPL-3.0 engine boundary, and dataset terms: [NOTICE.md](NOTICE.md).
