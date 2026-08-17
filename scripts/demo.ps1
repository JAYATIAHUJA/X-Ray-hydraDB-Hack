# X-Ray Evidence Platform — one-command demo walkthrough (Windows / PowerShell)
# Usage: .\scripts\demo.ps1
# Requires: Python >=3.11, uv, Node >=20, Docker Desktop (optional for live HydraDB)
$ErrorActionPreference = "Stop"

function Step { param([string]$msg) Write-Host "`n▶ $msg" -ForegroundColor Cyan }
function Ok   { param([string]$msg) Write-Host "  ✓ $msg" -ForegroundColor Green }
function Warn { param([string]$msg) Write-Host "  ⚠ $msg" -ForegroundColor Yellow }

Step "X-Ray Evidence Platform — demo walkthrough"
Write-Host "  HackHydra 2026 · Track 01 — Coordination Risk Intelligence"

# ── 1. Python environment ────────────────────────────────────────────────────
Step "Setting up Python workspace (uv sync)"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "  uv not found — installing via pip"
    pip install uv --quiet
}
uv sync --quiet
Ok "Python packages ready"

# ── 2. Node environment ──────────────────────────────────────────────────────
Step "Setting up Node workspace (npm install)"
npm install --silent
Ok "Node packages ready"

# ── 3. Contract tests ────────────────────────────────────────────────────────
Step "Running contract tests (no services required)"
uv run pytest tests/contract/ -q --tb=short 2>&1 | Select-Object -Last 8
Ok "Contract tests complete"

# ── 4. Demo fixture evaluation ───────────────────────────────────────────────
Step "Evaluating demo fixture (10-person org)"
uv run python -c @"
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
print(f'  Faultlines: {len(faults)}  (top: {faults[0].source_module_key!r} -> {faults[0].target_module_key!r}  tier={faults[0].tier!r})')
print(f'  Gaps: {len(gaps)}  (top phantom: {gaps[0].phantom_key!r}  reason={gaps[0].reason!r})')
"@
Ok "Demo fixture analysis complete"

# ── 5. Synthetic evaluation ──────────────────────────────────────────────────
Step "Running synthetic-500 evaluation (planted ground truth)"
uv run python scripts/eval_synth.py 2>&1 | Select-String "(precision|recall|ghost|faultline|gap|PASS|FAIL)" | Select-Object -First 20
Ok "Precision/recall evaluation complete"

# ── 6. API ───────────────────────────────────────────────────────────────────
Step "Starting API server on http://127.0.0.1:8000"
$apiJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    uv run uvicorn xray_api.app:app --host 127.0.0.1 --port 8000
}
Start-Sleep 3
try {
    $null = Invoke-WebRequest http://127.0.0.1:8000/api/v1/health -UseBasicParsing -TimeoutSec 5
    Ok "API healthy at http://127.0.0.1:8000"
} catch {
    Warn "API did not respond — check job output: Receive-Job $($apiJob.Id)"
}

# ── 7. Web UI ────────────────────────────────────────────────────────────────
Step "Starting web UI on http://localhost:5173"
$webJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    npm run dev --workspace=apps/web
}
Start-Sleep 3
Ok "Web UI starting at http://localhost:5173"

Write-Host ""
Write-Host "Demo ready." -ForegroundColor Green
Write-Host "  Landing page:   http://localhost:5173/"
Write-Host "  App (Org lens): http://localhost:5173/app"
Write-Host "  API health:     http://127.0.0.1:8000/api/v1/health"
Write-Host ""
Write-Host "  To load HydraDB live path:"
Write-Host "    docker compose --profile core up -d"
Write-Host "    Invoke-WebRequest -Method POST http://127.0.0.1:8000/api/v1/hydra/seed-fixture"
Write-Host ""
Write-Host "Press Enter to stop all background jobs."
$null = Read-Host
Stop-Job $apiJob, $webJob -ErrorAction SilentlyContinue
Remove-Job $apiJob, $webJob -ErrorAction SilentlyContinue
