# Judge demo runbook

Use the live workflow for judging. A reference-fallback screen is useful for
development, but it does not prove HydraDB execution.

## Start and verify

Prerequisites: Docker Desktop with the Linux engine running, Python 3.13, `uv`,
Node 22, and npm 10.

```powershell
./scripts/setup.ps1
```

The command now fails closed unless all of these are true:

1. Docker is ready.
2. The pinned HydraDB and MinIO runtime is healthy.
3. The demo graph seeds completely.
4. API health reports `hydra.status: live` and `graph_loaded: true`.
5. Owner, reverse-dependency, and abstention questions each execute a HydraDB query.
6. Live query p50/p95 is written to `docs/results/judge-latency.json`.

Open `http://127.0.0.1:5173/app`, then use this sequence:

1. Show **HydraDB live**, node/edge counts, and the active dataset in the header.
2. Ask: “Who owns payments-api now, and why did an older Jira record say Alex?”
3. Point out the trusted CODEOWNERS record, expired Jira record, policy, evidence,
   exact query, one round trip, and engine time.
4. Ask: “Which services are affected if ledger-worker changes?” and show the
   dependency-to-current-owner multi-hop path.
5. Ask: “Who approved the refund limit change?” and show the evidence-backed
   refusal to guess.
6. Open **Identity review**. Explain why unresolved aliases are excluded from risk
   scores until a human accepts the proposed merge.

## Verify an already-running API

```powershell
uv run python scripts/verify_judge_demo.py --api-base http://127.0.0.1:8000
```

This command exits non-zero on fallback execution, an unloaded graph, a degraded
query, or missing query proof.

## Stop

```powershell
./scripts/teardown.ps1 -RuntimeId runtime-demo
```

If Docker Desktop cannot start, do not present latency numbers or claim a live
demo. The committed `judge-latency.json` deliberately keeps p50/p95 null until a
real run succeeds.
