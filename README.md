<div align="center">

# X-Ray Evidence Platform

**Evidence-backed organizational graph analysis on self-hosted HydraDB.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://python.org)
[![Node](https://img.shields.io/badge/node-22+-green.svg)](https://nodejs.org)
[![HydraDB](https://img.shields.io/badge/HydraDB-pinned%20%2302a40025-blueviolet.svg)](infra/runtime-images.lock)

</div>

X-Ray turns offline engineering exports—Slack, email, JIRA, Confluence,
GitHub Issues, and git—into a typed graph. It answers ownership, authorship,
and review questions, then exposes coordination risks with links back to source
evidence.

It is an investigative aid, not an employee-scoring or defect-prediction
system. Structural position is not performance, and an absent record does not
prove that an action never happened.

## What it finds

| Lens | Question | Output |
|---|---|---|
| Ghost (structural centrality) | Who sits on many communication paths relative to formal rank? | Rank gap and bounded removal impact — not a performance score |
| Faultlines | Which dependent modules lack a communication path between owners? | Dependency evidence, owner confidence, and bridge suggestion |
| Gaps | Which required evidence step is absent from the corpus? | Phantom node, chain context, and export-window position |

Every finding can carry source IDs, confidence, content SHA-256, the executed
HydraDB query, limitations, and a recommended next action.

## Results

| Corpus | Result |
|---|---|
| Salesforce HERB, all 30 products | 5,126-person communication graph; Ghost #1 remains #1 after unresolved handles are removed; no fabricated faultlines or gaps |
| Apache Kafka, Mar–Jun 2025 | 292 people; 49 faultlines; 53 in-window dangling parents separated from 82 export-boundary cases |
| Synthetic 500-person org | Faultline and gap precision/recall 1.000/1.000; Ghost top-10 overlap 0.933 against exact betweenness |
| Kubernetes full-org demo (`kubernetes-demo`) | Snapshot analytics over `kubernetes` + `kubernetes-sigs`: Ghost (K8s Bridge Ops), network→api-machinery faultlines, missing KEP approval gap |
| Meshery OSS demo (`meshery-demo`) | Smaller snapshot corpus (optional): Ghost (Bridge Ops), ui→server faultlines, missing approval gap |

Reproducible outputs live in [docs/results](docs/results). Hosted Render defaults to
`XRAY_SNAPSHOT_DIR=data/snapshots/kubernetes-demo` (Snapshot analytics — not live HydraDB).
Refresh with `uv run python scripts/build_kubernetes_corpus.py`. Recording path:
[docs/judge-demo.md](docs/judge-demo.md)#kubernetes-snapshot-demo-recording.

## Quick start

Prerequisites: Docker, Python 3.13, [uv](https://docs.astral.sh/uv/), Node 22,
and npm 10.

Linux/macOS:

```bash
./scripts/setup.sh
```

Windows PowerShell:

```powershell
./scripts/setup.ps1
```

Judge path in under five minutes:

1. Run `setup` (fails closed unless HydraDB is live and seeded).
2. Open `http://127.0.0.1:5173/app`.
3. Run `uv run python scripts/verify_judge_demo.py`.
4. Read [`docs/results/judge-scorecard.json`](docs/results/judge-scorecard.json).

The setup command starts the pinned HydraDB/MinIO runtime, seeds the demo
fixture, and launches the API and web app. It prints the local URLs and teardown
command when ready. It also fails closed if HydraDB is not live, verifies three
Judge Mode queries, and records real query latency. See
[the judge demo runbook](docs/judge-demo.md).

To run only the database services:

```bash
./scripts/setup.sh --core-only
```

## Verify a clean clone

```bash
uv sync --locked
uv run ruff check apps packages scripts tests
uv run mypy
uv run pytest -q
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

Live HydraDB integration tests are opt-in locally and run against a real pinned
runtime in CI:

```bash
export XRAY_HYDRA_URI=bolt://127.0.0.1:17687
export XRAY_HYDRA_USER=neo4j
export XRAY_HYDRA_PASSWORD="$(tr -d '\r\n' < infra/runtime/runtime-demo/hydra-auth-token)"
uv run pytest -q -m integration tests/integration/test_hydradb_live.py
```

## Architecture

```text
offline exports
      │
      ▼
source adapters → identity map → canonical records + evidence
      │
      ▼
derived typed graph → HydraDB batch loader
      │
      ├── MSpaths: structural rank and owner reachability
      └── SPpaths: evidence-chain gaps
      │
      ▼
FastAPI → React dashboard / Markdown risk report
```

The API visibly reports whether a result came from live HydraDB or the bounded
in-process reference implementation. It never labels fallback execution as
live.

## Repository map

| Path | Purpose |
|---|---|
| `apps/api` | FastAPI routes, services, Hydra integration, schemas |
| `apps/web` | React dashboard and interactive 3D graph |
| `packages/xray_ingest` | Source adapters, identity resolution, canonicalization |
| `packages/xray_analytics` | Ghost, Faultline, Gap, and question analysis |
| `packages/xray_hydra` | Cypher compilation, gateway, and resumable loader |
| `packages/xray_runtime` | Isolated pinned runtime management |
| `data/fixtures` | Small deterministic fixtures and ground truth |
| `docs/results` | Checked-in evaluation and benchmark outputs |

## Data and safety boundaries

- X-Ray consumes offline exports; it does not require SaaS credentials.
- Identity merges require explicit mappings or stable source identifiers.
- Unresolved identities remain visible instead of being guessed together.
- Hosted deployments are read-only by default; imports and write operations
  require explicit configuration.
- Findings are coordination prompts that require human context.

## Deeper documentation

- [Verified HydraDB Cypher compatibility](docs/cypher-compat-verified.md)
- [Deployment notes](infra/deploy/README.md)

Licensed under Apache-2.0. HydraDB and MinIO runtime images retain their own
licenses; see [NOTICE.md](NOTICE.md).
