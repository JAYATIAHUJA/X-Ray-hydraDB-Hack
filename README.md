# X-Ray

> **The org chart says who reports to whom. X-Ray asks who actually keeps the work moving.**

`HackHydra 2026` · `HydraDB` · `Evidence-first engineering intelligence`

X-Ray is a hackathon project that maps an engineering organization as two connected graphs:
the **work graph** (code, modules, tickets, and dependencies) and the **human graph**
(who communicates, collaborates, and carries context). Comparing those graphs makes risks
visible that a document search or an org chart cannot show on its own.

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

## HydraDB in X-Ray

HydraDB is the graph layer behind the project. It is used for loading a canonical evidence
snapshot, reading the live people/communication graph, evaluating owner-to-owner communication
distances for Faultlines, and reading Phantom lineage for Gaps when a live instance is
configured.

The architecture keeps graph work graph-native and bounded rather than turning the API into a
large client-side traversal loop. A local in-memory fixture fallback remains available for
development when HydraDB is not configured.

## Current build

| Area | Status |
| --- | --- |
| Deterministic graph IDs and evidence snapshots | Built |
| Derived communication, ownership, dependency, and gap relationships | Built |
| Slack, email, ticket, and Git export adapters | Built for explicit exported facts |
| HydraDB gateway, loader, health check, and fixture seeding | Built |
| API and three-lens web interface | Built against the labelled demo fixture |
| Live source connectors and production data validation | In progress |
| HERB evaluation and incident-based validation | Planned |

The current demo data is synthetic and labelled. It demonstrates the product model; it is **not**
a measured claim about a real organization.

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

## Run locally

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

To run the mixed Slack/email/ticket/Git fixture, select it before starting the API:

```powershell
$env:XRAY_FIXTURE_VARIANT = "mixed"
```

To run the 500-person synthetic evaluation fixture:

```powershell
uv run python scripts/gen_synthetic_org.py
$env:XRAY_FIXTURE_VARIANT = "synth500"
```

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
uv run python scripts/eval_synth.py
```

Measured on `xray-synth-500` on 17 Aug 2026:

| Metric | Value |
| --- | ---: |
| Nodes / edges | 565 / 1,315 |
| Faultline precision | 0.429 |
| Faultline recall | 1.000 |
| Faultlines planted / returned | 3 / 7 |
| Gap precision | 1.000 |
| Gap recall | 1.000 |
| Gaps planted / returned | 5 / 5 |
| Ghost top-1 hit rate across seeds | 1.000 |
| Ghost mean top-10 overlap vs exact betweenness | 1.000 |

The faultline result is intentionally reported as precision/recall against planted labels, not
as proof of incidents. The four non-planted returned pairs are coordination-debt findings in the
synthetic graph, but they are counted as false positives for planted-truth scoring.

## Validation philosophy

X-Ray will report negative results as plainly as positive ones. In particular:

- A Faultline is coordination debt, not a claimed future incident, unless validation data
  supports that stronger conclusion.
- Ghost scores use bounded path analysis and should be compared with simpler degree baselines.
- Gaps represent structural incompleteness, never automatic evidence of deletion.

## Attribution

- [HydraDB](https://github.com/hydra-db/hydradb) for the graph database runtime.
- [Salesforce HERB](https://huggingface.co/datasets/Salesforce/HERB) is the planned evaluation
  dataset; its data is not included in this repository.
- Built for HackHydra by Jayati.

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE).
