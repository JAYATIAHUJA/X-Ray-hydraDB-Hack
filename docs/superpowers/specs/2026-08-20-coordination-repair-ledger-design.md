# Coordination Repair Ledger + eval suite (Approach A)

**Status:** Approved by user 2026-08-20  
**Scope:** Hackathon-ready thin slice on existing X-Ray architecture

## Goal

Ship four deliverables judges can see:

1. `xray-demo-v2` fixture with conflict, impact, phantom, identity merge, ghost
2. Coordination Repair Ledger: propose → approve → re-check → gap closed
3. PlanGraph-style baseline benchmark (honest, synthetic)
4. Blinded retrospective study harness + results

## Non-goals

Full SaaS workflow, SSO, email, or claiming a live enterprise pilot.

## Design

### demo-v2

Clone `xray-demo` → `data/fixtures/xray-demo-v2/` with `dataset_id: xray-demo-v2`.
Add/ensure: owner conflict, dependency impact, missing-approval phantom, identity merge candidate, ghost broker.
Register `demo-v2` in `FIXTURE_VARIANTS`.

### Repair Ledger

- Proposals derived from open faultlines/gaps (non-personnel: backup owner, CODEOWNERS, runbook, second approver, cross-team review).
- Verdict: SUPPORTED / UNSUPPORTED / UNKNOWN from evidence.
- Approve via write-token; store overlay edges/artifacts on the active snapshot.
- Verify re-runs the same lens on the overlayed bundle; closed when finding disappears.
- UI view: `repairs`.

### PlanGraph baseline

Script compares naïve client multi-query BFS / first-edge ownership vs X-Ray typed ranking + one-shot path accounting. Writes `docs/results/plan-graph-baseline.json`. Does not claim to be the PlanGraph product.

### Blinded retrospective

Sealed labels in `data/eval/blinded_labels.json`. Eval computes predictions first, then scores. Writes `docs/results/blinded-retrospective.json` with limitations.
