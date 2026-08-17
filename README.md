# X-Ray

> **The org chart says who reports to whom. X-Ray shows who actually keeps the work moving —
> and where the graph says a conversation or a record should exist and doesn't.**

`HackHydra 2026 · Track 01` · self-hosted open-source **HydraDB** (pinned) · Apache-2.0

X-Ray reads exports from mail, tickets, git and Slack, builds **two graphs** — the *work graph*
(modules, dependencies, changes) and the *human graph* (who replies to whom) — and finds the
**missing edges between them**: technical dependency without conversation, evidence chains
without their required link, and the people every path quietly routes through. That signal is an
*absence in one graph where a corresponding edge exists in the other*; a vector index has no way
to express it. HydraDB's bounded path procedures do.

**One command, no API keys:**

```powershell
./scripts/setup.sh    # HydraDB + MinIO (compose) → API → seed → web (Windows: scripts\setup.ps1)
```

**Measured, traceable, honest** (every number links to a checked-in results file):

| | Apache Kafka, Mar–Jun 2025 (real, public) | Labelled synthetic org (500 people) |
| --- | --- | --- |
| Load-bearing person | Chia-Ping Tsai (PMC) — structural #1 · formal #4 | Priya Nair — senior engineer, structural #1 · **formal #33** |
| Largest rank gap in top 10 | **PoAn Yang, committer — #5 vs #34 (+29)** | — |
| What-if removal | 516 of 6,295 reachable pairs lose their ≤4-hop path | **110,883 of 124,251** |
| Uncoordinated dependencies | 49 (top: `clients` ↔ `connect`, co-changed 9×, no reply path) | 3 planted / 3 found, 0 false positives (negative control) |
| Structurally missing records | 135 (dangling thread parents at the export boundary) | 5 planted / 5 found |
| Incident lift | **not measurable** — reported as coordination debt only | — |
| Engine vs client | 1 pairwise `algo.MSpaths` call replaces 42,486 per-pair queries | 1 call replaces 124,750 |

Sources: [docs/results/kafka-2025q2.json](docs/results/kafka-2025q2.json) ·
[docs/results/synth500.json](docs/results/synth500.json) ·
[docs/cypher-compat-verified.md](docs/cypher-compat-verified.md) (what the pinned engine
actually accepts, measured, not assumed).

**Where HydraDB does the work:** one pairwise `algo.MSpaths` call for the Ghost sample and one
for Faultline reachability; `algo.SPpaths` for the chain of custody through a `Phantom`;
integer-id / `path_key` resolution outside the engine; every query dataset-scoped and bounded
(`maxLen` 4 / 8). The UI shows the exact executed statement, its parameters, engine time, and the
client-side equivalent next to every lens.

**What we do not claim:** that a faultline predicts an incident (the literature is contested and
this corpus has no module-linked incident signal); that a missing record was deleted (the corpus
is structurally incomplete at that point); exact betweenness (it is a bounded, sampled tally,
stated as such); or that a private company's data would look like Apache Kafka's.

---

## Thesis

Enterprise context is not just text retrieval. The important signal is often graph structure:
who sits between teams, which module dependencies have no matching communication path, and where
an expected evidence chain has a missing step. X-Ray keeps those questions explicit and bounded:
HydraDB evaluates paths over typed edges and integer node IDs; the API reports degraded fallback
states instead of pretending fixture analysis is live graph execution.

## The problem

The most important parts of an engineering organization are rarely written down in one place.
They are scattered across Slack, email, tickets, code, and hand-offs between teams.

That makes three questions difficult to answer before something breaks:

1. Who is quietly load-bearing, even if their formal title does not show it?
2. Which technical dependencies lack the human coordination they need?
3. Where does an evidence trail require a record that is missing?

## What X-Ray reveals

| Lens | Question | Signal |
| --- | --- | --- |
| **Ghost** | Who is structurally load-bearing? | People whose removal disconnects otherwise reachable collaboration paths. |
| **Faultline** | Where does work depend on work without enough coordination? | Module dependencies whose likely owners have no, or only weak, communication path. |
| **Gaps** | Where is an expected evidence step absent? | A `Phantom` node inserted for a required sequence gap or a dangling thread parent. |

Every finding keeps the source evidence visible in the UI: record IDs, source type, confidence,
evidence class, `content_sha256`, redacted excerpt, limitations, executed HydraDB query, and one
recommended action.

## How it works

```text
Slack · Email · Tickets · Git
              ↓
  explicit identity + evidence normalization
              ↓
People · Artifacts · Modules
              ↓
COMMUNICATES · OWNS · DEPENDS_ON · Phantom
              ↓
Ghost · Faultline · Gaps
```

### Evidence before inference

X-Ray is deliberately conservative:

- Source adapters accept explicit IDs, recipients, reply authors, and module references.
  They do **not** guess these facts from message text.
- Identities are resolved before data reaches the graph, then assigned stable integer IDs.
- Derived edges retain their source evidence, so a relationship can be traced back to the
  facts that created it.
- Traversals are bounded. A path is useful only when its length stays meaningful.

This distinction matters: **a missing record is not proof that somebody deleted it.** It means
the available corpus is structurally incomplete at that point; export filtering and missing
sources remain possible explanations.

## How HydraDB is used

HydraDB is the graph layer behind the project. It does real query work in the live path:

- The loader writes canonical nodes and edges with `UNWIND` batches.
- Ghost uses one bounded `algo.MSpaths` call over `COMMUNICATES` paths to score sampled
  intermediates. The API exposes the exact query text, parameters, max length, round trips, and
  engine time.
- Faultlines use one bounded owner-to-owner path query for the candidate pairs instead of an
  unbounded client traversal loop or a per-pair query storm.
- Gaps use `algo.SPpaths` over `PRECEDED_BY` between the selected artifact endpoints to show the
  chain around a `Phantom` evidence hop.
- Live graph lookup avoids string matching in query predicates for the analysis path. Canonical
  keys are resolved to deterministic 63-bit integer IDs or procedure-safe `path_key` values before
  HydraDB executes path procedures.

The architecture keeps graph work graph-native and bounded rather than turning the API into a
large client-side traversal loop. A local in-memory fixture fallback remains available for
development when HydraDB is not configured.

The live HydraDB dialect is pinned and documented in
[docs/cypher-compat-verified.md](docs/cypher-compat-verified.md). The verified rules matter:
writes use auto-commit sessions, node resolution is by integer `id` or canonical `path_key`
depending on the HydraDB procedure, relationship traversals are bounded, and unsupported generic
scans/counts are avoided.

## Current build

| Area | Status |
| --- | --- |
| Deterministic graph IDs and evidence snapshots | Built |
| Derived communication, ownership, dependency, and gap relationships | Built |
| Slack, email, ticket, and Git export adapters | Built for explicit exported facts |
| HydraDB gateway, loader, health check, and fixture seeding | Built |
| API and three-lens web interface | Built with live/fallback status, graph layout, evidence drawer, and query card |
| Synthetic 500-person fixture and planted-truth evaluation | Built |
| Real corpus: Apache Kafka (mbox + JIRA + git) through the export adapters, offline identity map | Built; snapshot ships in the repo |
| What-if removal, engine-vs-client comparison, SPpaths chain rendering | Built |
| Live source connectors | Out of scope for this hackathon; export adapters are the supported path |
| HERB evaluation and incident-based validation | Not included; no incident lift is claimed |

Measured corpora are a labelled synthetic organization and one public open-source project. Neither
is a claim about a private company.

## Source ingestion

The ingestion layer currently normalizes deterministic exports before they enter the canonical
evidence pipeline.

| Export | Adapter | Required fields |
| --- | --- | --- |
| Slack message | `slack_records` | `id`, `occurred_at_epoch`, `author_id` |
| Email | `email_records` | `id`, `occurred_at_epoch`, `from_id`, `to_ids` |
| Ticket | `ticket_records` | `id`, `occurred_at_epoch`, `reporter_id` |
| Git commit | `code_records` | `sha`, `occurred_at_epoch`, `author_id` |

Each adapter accepts `module_keys` when the export contains an explicit module reference. Slack
also accepts resolved `parent_author_id` and `mentions`; email recipients become observed
communication inputs. Directory records for referenced people and modules must be present in the
same bundle before relationships are derived.

The `ingest_exports` runner combines all four adapters with directory records and executes the
full `canonicalize → derive → detect gaps` pipeline in one deterministic build. Existing
canonical exports can also be passed through the same boundary while a source is being migrated.
Git rows may declare `dependency_keys` to create explicit `DEPENDS_ON` evidence.

### Bring your own exports

Real exports identify people by email address, Slack user id, or JIRA account id. X-Ray resolves
those **offline, in Python, before anything reaches the graph** through an explicit identity map;
it never fuzzy-matches inside the engine. Ids that are not in the map are kept as visible
`unresolved-…` handles with a bundle limitation, so a partial map degrades honestly instead of
failing.

```powershell
git log --name-only --format="%x1e%H%x1f%at%x1f%ae%x1f%s%x1f%b" > git.log

uv run python scripts/ingest_export.py `
  --dataset-id my-team `
  --directory directory.json `          # people / teams / modules as canonical records
  --identity-map identity.json `        # {"alice@example.com": "alice", "U0123": "alice"}
  --mbox dev.mbox `                     # mailing list or mailbox export
  --jira-csv jira.csv `                 # JIRA CSV export
  --git-log git.log --module-prefixes modules.json `   # {"services/payments": "payments-api"}
  --slack-dir slack-export/ `           # one folder per channel
  --out data/snapshots/my-team
```

Adapters: `mbox_rows` (From/To/Cc/In-Reply-To headers), `jira_csv_rows`, `git_log_rows`
(0x1e-separated commits, `Depends-On:` trailers become explicit dependencies), and
`slack_export_rows` (explicit user ids, thread parents kept even when the parent message is
absent — that absence is what the Gaps lens surfaces). Live OAuth connectors are intentionally
out of scope for this build.

## Setup

### Requirements

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- Node.js 22+ and npm 10+
- Docker Desktop only when running a local HydraDB + MinIO stack

### API + web development

```powershell
uv sync

$env:PYTHONPATH = "apps/api/src;packages/xray_analytics/src;packages/xray_core/src;packages/xray_hydra/src;packages/xray_ingest/src;packages/xray_runtime/src"
uv run uvicorn xray_api.app:app --reload
```

In a second terminal:

```powershell
npm install
$env:VITE_XRAY_API_BASE_URL = "http://127.0.0.1:8000"
npm run dev
```

Without `XRAY_HYDRA_URI`, the API intentionally stays in fixture fallback mode. Its health
endpoint reports `fallback`, `live`, or `offline` so the UI never implies that a live graph
database is available when it is not.

To run the 500-person synthetic evaluation fixture:

```powershell
uv run python scripts/gen_synthetic_org.py
$env:XRAY_FIXTURE_VARIANT = "synth500"
```

### One-command local stack

On Windows:

```powershell
scripts\setup.ps1
```

On macOS/Linux:

```sh
./scripts/setup.sh
```

The setup script prepares the local HydraDB + MinIO runtime, syncs Python dependencies, starts
the API, seeds the fixture, installs web dependencies, starts the Vite UI, and prints API/web
URLs. Use `-CoreOnly` / `--core-only` to start only the database runtime.

Expected result after setup: the web header shows `HydraDB: live` with node and edge counts.
If HydraDB is not configured or unavailable, the header shows `fallback` or `offline` and the
API labels lens responses accordingly.

### Configure HydraDB

Set these variables before starting the API:

```powershell
$env:XRAY_HYDRA_URI = "bolt://localhost:7687"
$env:XRAY_HYDRA_USER = "neo4j"
$env:XRAY_HYDRA_PASSWORD = "password"
$env:XRAY_HYDRA_DATABASE = "neo4j"
```

Then seed the bundled fixture:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/hydra/seed-fixture
```

The pinned HydraDB container image and local MinIO topology live in
[infra/runtime-images.lock](infra/runtime-images.lock) and [compose.yaml](compose.yaml). The
current HydraDB source commit is `02a40025d2d57e97ab2754c8256219cdbfeab379`. For the engine
stack, set `RUST_MIN_STACK=33554432`; the compose configuration already applies this value.

### Measured ingest throughput

The live local benchmark writes 10,000 synthetic `COMMUNICATES` relationships through the same
`UNWIND` batch path used by the loader. Node setup is excluded from the timing.

Command:

```powershell
uv run python scripts/bench_ingest.py --edges 10000 --people 500
```

Measured on the local HydraDB + MinIO runtime on 16 Aug 2026:

| Batch size | Edges | Seconds | Edges/sec | Status |
| ---: | ---: | ---: | ---: | --- |
| 500 | 10,000 | 2.302 | 4,344 | ok |
| 1,000 | 10,000 | 2.460 | 4,065 | ok |
| 2,000 | 10,000 | - | - | failed: HydraDB admission control limit |
| 5,000 | 10,000 | - | - | failed: HydraDB admission control limit |

Loader default: `batch_size=500`. Larger batches are not automatically better here; this
runtime rejects query batches above 1024 items.

## Evaluation

Synthetic evaluation is reproducible with:

```powershell
uv run python scripts/eval_synth.py --json docs/results/synth500.json
```

Every number below traces to [docs/results/synth500.json](docs/results/synth500.json), which is
stamped with the pinned HydraDB digest and source commit. Measured on `xray-synth-500` on
17 Aug 2026:

| Metric | Value |
| --- | ---: |
| Nodes / edges | 565 / 1,319 |
| Faultline precision | 1.000 |
| Faultline recall | 1.000 |
| Faultlines planted / returned | 3 / 3 |
| Gap precision | 1.000 |
| Gap recall | 1.000 |
| Gaps planted / returned | 5 / 5 |
| Ghost top-1 hit rate across seeds | 1.000 |
| Ghost mean top-10 overlap vs exact betweenness | 0.933 |
| What-if: remove the planted Ghost | 110,883 of 124,251 reachable pairs lose their ≤4-hop path |
| Client baseline (bounded all-pairs BFS, 500 people) | ≈400 ms ≈ 124,750 per-pair shortest-path calls |

The faultline result is intentionally reported as precision/recall against planted labels, not
as proof of incidents. The fixture includes a negative control: four coordinated dependencies whose
owners communicate directly. Those must *not* be flagged, and are not. The planted Ghost is
`Priya Nair`, a senior engineer who ranks structurally #1 and formally #33 (rank gap +32); she is
not the top of the reporting chain, which is the point of the lens.

The API exposes the same numbers live: `GET /api/v1/snapshots/{id}/ghosts?exclude=person:...`
returns a `what_if` block (pairs lost without that person) and a `comparison` block (engine
round trip vs the in-process BFS baseline, and the number of per-pair calls one pairwise
`algo.MSpaths` call replaces).

### Real corpus: Apache Kafka, March–June 2025

The same pipeline was run on public Apache Kafka exports — `dev@kafka.apache.org` mbox
(4 months), the KAFKA JIRA CSV export, and `git log --name-only` — with formal seniority taken
from the public ASF roster (PMC = 4, committer = 3, contributor = 1). Identity is resolved
offline by exact joins only (ASF id, email, case-folded public name). Every number traces to
[docs/results/kafka-2025q2.json](docs/results/kafka-2025q2.json); the snapshot ships in
`data/snapshots/kafka-2025q2` so it runs without downloading anything:

```powershell
$env:XRAY_SNAPSHOT_DIR = "data/snapshots/kafka-2025q2"
uv run uvicorn xray_api.app:app --reload
```

| Metric | Value |
| --- | ---: |
| Nodes / edges | 2,294 / 4,476 (292 people, 26 modules, 1,841 artifacts, 135 phantoms) |
| Sources | 850 person-to-person emails · 397 tickets · 597 commits |
| Identity | 292 people, 12 unresolved source ids kept visibly; 28 PMC + 9 committers matched to the roster |
| Ghost #1 | Chia-Ping Tsai (PMC) — structural #1, formal #4 |
| Largest rank gap in the top 10 | **PoAn Yang, committer — structural #5, formal #34 (+29)**; TengYao Chi, committer — #8 vs #30 |
| What-if: remove the #1 | 516 of 6,295 reachable pairs lose their ≤4-hop reply path |
| Faultlines | 49 (48 `no_path`, 1 `weak_coordination`); top: `clients` ↔ `connect` co-changed 9× with no dev@ reply path between their top authors |
| Incident lift | **Not measurable** — 1 of 397 issues in the window carries a component, so no lift over a churn baseline is claimed. Coordination debt only. |
| Client baseline | bounded all-pairs BFS over 292 people ≈ 48 ms ≈ 43,071 per-pair calls |

Two honest notes from this run. First, mailing-list mail is addressed to the list, so the
person-to-person signal is *reply → parent author* (an `In-Reply-To` whose parent is in the
corpus), not `To:`; that is what the mbox adapter emits. Second, identity quality changes the
findings: an earlier build split `jsancio` into two handles and reported a `core ↔ metadata`
faultline between them — merging on the exact ASF id removed it, because those two people talk.
Faultline output is only as good as the identity map, which is why unresolved ids are surfaced
rather than hidden.

## Scale and limitations

X-Ray will report negative results as plainly as positive ones. In particular:

- A Faultline is coordination debt, not a claimed future incident, unless validation data
  supports that stronger conclusion.
- Ghost scores use bounded path analysis and should be compared with simpler degree baselines.
- Gaps represent structural incompleteness, never automatic evidence of deletion.
- Sampling keeps Ghost queries bounded on larger graphs; `maxLen=4` is a product choice, not a
  universal organization-science claim.
- Measured corpora are one labelled synthetic org and one public open-source project (Apache
  Kafka); neither is a claim about a private company. Live OAuth connectors are intentionally
  out of scope; the export adapters (mbox, JIRA CSV, git log, Slack export JSON) are the path in.
- HERB evaluation remains planned if time allows; it is not included in the repository.

## Demo path

The intended demo sequence is under three minutes:

1. Start on the org graph and toggle `Official rank` to `Actual normalized` to show the
   load-bearing person become visually larger.
2. Open the Ghost evidence drawer and show the sampled centrality, bus-factor impact, source
   evidence, and recommended backup-owner action.
3. Switch to Faultlines and show the red highlighted dependency where module owners lack a short
   communication path.
4. Switch to Gaps, choose the source/target artifacts, and show the phantom hop in the timeline.
5. Open the HydraDB query card and point to `algo.MSpaths` / `algo.SPpaths`, bounded `maxLen`,
   one round trip, and measured engine time.
6. End on this README's throughput and evaluation tables.

## Verification

Commands used before submission-oriented commits:

```powershell
uv run pytest
uv run mypy
npm --prefix apps/web run typecheck
npm --prefix apps/web test
npm --prefix apps/web run lint
npm --prefix apps/web run build
```

The Vite/Vitest commands may need normal Windows process-spawn permission; in restricted
sandboxes they can fail with `spawn EPERM` even when the code is valid.

## Attribution

- [HydraDB](https://github.com/hydra-db/hydradb) for the graph database runtime.
- [Salesforce HERB](https://huggingface.co/datasets/Salesforce/HERB) is the planned evaluation
  dataset; its data is not included in this repository.
- Built for HackHydra by Jayati.

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE). Third-party
components, the AGPL-3.0 engine boundary, and dataset terms are listed in [NOTICE.md](NOTICE.md).
