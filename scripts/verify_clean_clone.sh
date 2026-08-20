#!/usr/bin/env bash
# X-Ray Evidence Platform — clean-clone verification
# Simulates what a judge/reviewer sees when they clone the repo fresh.
# Usage: bash scripts/verify_clean_clone.sh
# Requires: Python >=3.11, uv, Node >=20
set -euo pipefail

BOLD='\033[1m'; TEAL='\033[36m'; GREEN='\033[32m'; RED='\033[31m'; RESET='\033[0m'
step() { echo -e "\n${BOLD}${TEAL}▶ $*${RESET}"; }
ok()   { echo -e "  ${GREEN}✓ $*${RESET}"; }
fail() { echo -e "  ${RED}✗ $*${RESET}"; exit 1; }

step "Verifying repository from a clean-clone perspective"

# 1. Workspace sync
step "uv sync (Python packages)"
uv sync --quiet && ok "Python workspace ready" || fail "uv sync failed"

step "npm install (Node packages)"
npm install --silent && ok "Node workspace ready" || fail "npm install failed"

# 2. Type-checking
step "mypy type check"
uv run mypy packages/ apps/api/src/ --ignore-missing-imports --no-error-summary -q \
  && ok "mypy passed" || fail "mypy reported errors"

# 3. Linting
step "ruff lint"
uv run ruff check packages/ apps/api/src/ tests/ --quiet \
  && ok "ruff passed" || fail "ruff reported lint errors"

# 4. Contract tests (no services)
step "pytest tests/contract/ (no services required)"
uv run pytest tests/contract/ -q --tb=short \
  && ok "All contract tests passed" || fail "Contract tests failed"

# 5. API tests
step "pytest apps/api/tests/ (no services required)"
uv run pytest apps/api/tests/ -q --tb=short \
  && ok "All API tests passed" || fail "API tests failed"

# 6. Frontend type check
step "tsc --noEmit (TypeScript)"
(cd apps/web && npx tsc --noEmit) \
  && ok "TypeScript check passed" || fail "TypeScript check failed"

# 7. Frontend tests
step "vitest run (frontend tests)"
(cd apps/web && npx vitest run --reporter=dot) \
  && ok "Vitest tests passed" || fail "Vitest tests failed"

# 8. Fixture integrity
step "Verifying fixture files exist"
for f in data/fixtures/xray-demo/directory.json \
          data/fixtures/xray-demo/events.json \
          data/fixtures/xray-demo/git_facts.json \
          data/fixtures/xray-demo/manifest.json \
          data/snapshots/kafka-2025q2/manifest.json \
          data/snapshots/meshery-demo/manifest.json \
          data/snapshots/kubernetes-demo/manifest.json; do
  [[ -f "$f" ]] && ok "$f" || fail "Missing: $f"
done

# 9. Results files
step "Verifying benchmark result files"
for f in docs/results/latency.json docs/results/throughput.json \
          docs/results/synth500.json docs/results/kafka-2025q2.json; do
  [[ -f "$f" ]] && ok "$f" || fail "Missing: $f"
done

echo ""
echo -e "${BOLD}${GREEN}Clean-clone verification PASSED.${RESET}"
echo "  All checks completed without a running database or external services."
