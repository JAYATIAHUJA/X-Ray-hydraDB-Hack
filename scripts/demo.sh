#!/usr/bin/env bash
# X-Ray Evidence Platform — one-command demo walkthrough
# Usage: bash scripts/demo.sh
# Requires: Python >=3.11, uv, Node >=20, Docker (optional for live HydraDB)
set -euo pipefail

BOLD='\033[1m'
TEAL='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RESET='\033[0m'

step() { echo -e "\n${BOLD}${TEAL}▶ $*${RESET}"; }
ok()   { echo -e "  ${GREEN}✓ $*${RESET}"; }
warn() { echo -e "  ${YELLOW}⚠ $*${RESET}"; }

step "X-Ray Evidence Platform — demo walkthrough"
echo "  HackHydra 2026 · Track 01 — Coordination Risk Intelligence"

# ── 1. Python environment ────────────────────────────────────────────────────
step "Setting up Python workspace (uv sync)"
if ! command -v uv &>/dev/null; then
  echo "  uv not found — installing via pip"
  pip install uv --quiet
fi
uv sync --quiet
ok "Python packages ready"

# ── 2. Node environment ──────────────────────────────────────────────────────
step "Setting up Node workspace (npm install)"
npm install --silent
ok "Node packages ready"

# ── 3. Contract tests ────────────────────────────────────────────────────────
step "Running contract tests (no services required)"
uv run pytest tests/contract/ -q --tb=short 2>&1 | tail -5
ok "All contract tests passed"

# ── 4. Demo fixture evaluation ───────────────────────────────────────────────
step "Evaluating demo fixture (10-person org)"
uv run python -c "
import json
from pathlib import Path
from xray_analytics import ghost_scores, faultlines, gap_findings
from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_ingest.pipeline import build_bundle

root = Path('data/fixtures/xray-demo')
records = []
for name in ('directory.json', 'events.json', 'git_facts.json'):
    records.extend(CanonicalRecord.model_validate(p) for p in json.loads((root / name).read_text()))
m = json.loads((root / 'manifest.json').read_text())
contracts = SequenceContractSet.model_validate({'contracts': m['sequence_contracts'], 'limitations': m['limitations']})
bundle = build_bundle(records, contracts, 'xray-demo-v1')

ghosts = ghost_scores(bundle)
faults = faultlines(bundle)
gaps = gap_findings(bundle)

print(f'  Ghost #1: {ghosts[0].display_name!r}  structural_rank={ghosts[0].structural_rank}  formal_rank={ghosts[0].formal_rank}  rank_gap=+{ghosts[0].rank_gap}')
print(f'  Faultlines: {len(faults)}  (top: {faults[0].source_module_key!r} → {faults[0].target_module_key!r}  tier={faults[0].tier!r})')
print(f'  Gaps: {len(gaps)}  (top phantom: {gaps[0].phantom_key!r}  reason={gaps[0].reason!r})')
"
ok "Demo fixture analysis complete"

# ── 5. Synthetic evaluation (precision/recall) ────────────────────────────────
step "Running synthetic-500 evaluation (planted ground truth)"
uv run python scripts/eval_synth.py 2>&1 | grep -E "(precision|recall|ghost|faultline|gap|PASS|FAIL)" | head -20
ok "Precision/recall evaluation complete"

# ── 6. Start API + Web (optional) ────────────────────────────────────────────
step "Starting API server on http://127.0.0.1:8000"
if lsof -i:8000 &>/dev/null 2>&1; then
  warn "Port 8000 already in use — skipping API start (may already be running)"
else
  uv run uvicorn xray_api.app:app --host 127.0.0.1 --port 8000 &
  API_PID=$!
  sleep 2
  if curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
    ok "API healthy at http://127.0.0.1:8000"
  else
    warn "API did not respond; check uvicorn output above"
  fi
fi

step "Starting web UI on http://localhost:5173"
if lsof -i:5173 &>/dev/null 2>&1; then
  warn "Port 5173 already in use — skipping Vite start"
else
  npm run dev --workspace=apps/web &
  WEB_PID=$!
  sleep 3
  ok "Web UI starting at http://localhost:5173"
fi

echo ""
echo -e "${BOLD}${GREEN}Demo ready.${RESET}"
echo "  Landing page:  http://localhost:5173/"
echo "  App (Org lens): http://localhost:5173/app"
echo "  API health:    http://127.0.0.1:8000/api/v1/health"
echo ""
echo "  To load HydraDB live path:"
echo "    docker compose --profile core up -d"
echo "    curl -X POST http://127.0.0.1:8000/api/v1/hydra/seed-fixture"
echo ""
echo "  Press Ctrl+C to stop."
wait
