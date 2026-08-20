#!/usr/bin/env sh
set -eu

STARTED_AT=$(python -c "import time; print(time.time())")
RUNTIME_ID="runtime-demo"
PROJECT="xray-runtime-demo"
API_PORT="8000"
WEB_PORT="5173"
CORE_ONLY=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --core-only) CORE_ONLY=1 ;;
    --runtime-id) shift; RUNTIME_ID="$1" ;;
    --project) shift; PROJECT="$1" ;;
    --api-port) shift; API_PORT="$1" ;;
    --web-port) shift; WEB_PORT="$1" ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

RUNTIME_DIR="infra/runtime/$RUNTIME_ID"
ENV_FILE="$RUNTIME_DIR/compose.env"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not ready. Start Docker and wait until 'docker info' succeeds." >&2
  exit 1
fi

uv sync --locked

if [ -f "$ENV_FILE" ]; then
  docker compose --env-file "$ENV_FILE" -p "$PROJECT" -f compose.yaml -f compose.test.yaml --profile core up -d --wait
else
  uv run python -m xray_runtime.manager start \
    --runtime-id "$RUNTIME_ID" \
    --compose-project "$PROJECT"
fi

if [ "$CORE_ONLY" -eq 1 ]; then
  echo "HydraDB runtime is live. Env file: $ENV_FILE"
  exit 0
fi

XRAY_HYDRA_URI="bolt://127.0.0.1:17687"
XRAY_HYDRA_USER="neo4j"
XRAY_HYDRA_PASSWORD="$(tr -d '\r\n' < "$RUNTIME_DIR/hydra-auth-token")"
XRAY_HYDRA_DATABASE="xray"
export XRAY_HYDRA_URI XRAY_HYDRA_USER XRAY_HYDRA_PASSWORD XRAY_HYDRA_DATABASE
export VITE_XRAY_API_BASE_URL="http://127.0.0.1:$API_PORT"

uv run uvicorn xray_api.app:app --host 127.0.0.1 --port "$API_PORT" > "$RUNTIME_DIR/api.log" 2>&1 &
echo "$!" > "$RUNTIME_DIR/api.pid"

python - <<PY
import time
import urllib.request

deadline = time.time() + 90
url = "http://127.0.0.1:$API_PORT/api/v1/health"
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status == 200:
                raise SystemExit(0)
    except OSError:
        time.sleep(1)
raise SystemExit(f"timed out waiting for {url}")
PY

python - <<PY
import json
import urllib.request

request = urllib.request.Request(
    "http://127.0.0.1:$API_PORT/api/v1/hydra/seed-fixture",
    method="POST",
)
with urllib.request.urlopen(request, timeout=60) as response:
    payload = json.loads(response.read().decode("utf-8"))
    print(json.dumps(payload, indent=2))
    if payload["status"] != "complete":
        raise SystemExit(f"HydraDB seed did not complete: {payload['detail']}")
PY

uv run python scripts/verify_judge_demo.py --api-base "http://127.0.0.1:$API_PORT"
uv run python scripts/bench_judge_latency.py

npm ci
npm run dev -- --port "$WEB_PORT" > "$RUNTIME_DIR/web.log" 2>&1 &
echo "$!" > "$RUNTIME_DIR/web.pid"

ELAPSED=$(python -c "import time; print(round(time.time() - $STARTED_AT, 1))")
echo "X-Ray is running in ${ELAPSED}s"
echo "API: http://127.0.0.1:$API_PORT/api/v1/health"
echo "Web: http://127.0.0.1:$WEB_PORT"
echo "Teardown: scripts/teardown.sh --runtime-id $RUNTIME_ID"
