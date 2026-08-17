# NOTICE

X-Ray is licensed under the Apache License 2.0 (see [LICENSE](LICENSE)). It builds on the
open-source software and data listed below. Nothing here is vendored into this repository;
each dependency is obtained from its upstream source under its own license.

## Graph engine (external service, not redistributed)

| Component | License | How X-Ray uses it |
|---|---|---|
| [HydraDB](https://github.com/hydra-db/hydradb) — pinned image `ghcr.io/hydra-db/hydradb@sha256:db78309a…cdb709`, source commit `02a40025d2d57e97ab2754c8256219cdbfeab379` | AGPL-3.0 | Runs as a separate container. X-Ray talks to it only over Bolt as a client and does not link, modify, or ship HydraDB source. The AGPL therefore governs the engine, not this repository. |
| [MinIO](https://github.com/minio/minio) | AGPL-3.0 | Local S3-compatible object store backing HydraDB in the compose stack. Separate container, client access only. |

## Python

| Package | License |
|---|---|
| neo4j (Bolt driver) | Apache-2.0 |
| FastAPI, uvicorn, Starlette | MIT / BSD-3-Clause |
| pydantic | MIT |
| polars | MIT |
| jsonschema | MIT |
| PyYAML | MIT |
| networkx (baseline betweenness only, never in the query path) | BSD-3-Clause |
| pytest, hypothesis, mypy, ruff (dev) | MIT / MPL-2.0 / MIT / MIT |

## Web

| Package | License |
|---|---|
| React, react-dom | MIT |
| @tanstack/react-query | MIT |
| Cytoscape.js | MIT |
| Vite, Vitest, TypeScript, ESLint (dev) | MIT / MIT / Apache-2.0 / MIT |
| Inter, JetBrains Mono (via @fontsource, self-hosted) | SIL OFL 1.1 |

## Data

| Dataset | License / terms | Status |
|---|---|---|
| `xray-demo`, `xray-synth-500` (bundled) | Apache-2.0 (this repository) | Synthetic, labelled; not a measurement of any real organisation. |
| [Salesforce HERB](https://huggingface.co/datasets/Salesforce/HERB) | See dataset card | Planned evaluation corpus; **not included** in this repository. |
| Public Apache Software Foundation mailing-list / JIRA / git exports | Apache-2.0 (ASF) | Optional real-corpus runs via the export adapters; not bundled. |

## AI assistance

Parts of this codebase were written with AI coding assistants (Anthropic Claude via Claude Code).
All engine behaviour documented in `docs/cypher-compat-verified.md` was measured against the
pinned HydraDB build, not inferred.
