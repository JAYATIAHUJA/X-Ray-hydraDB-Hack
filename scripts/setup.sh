#!/usr/bin/env sh
set -eu

CORE_ONLY=0
RUNTIME_ID=""
PROJECT=""
OBJECT_PREFIX="demo/xray-demo"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --core-only) CORE_ONLY=1 ;;
    --runtime-id) shift; RUNTIME_ID="$1" ;;
    --project) shift; PROJECT="$1" ;;
    --object-prefix) shift; OBJECT_PREFIX="$1" ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ -z "$RUNTIME_ID" ] || [ -z "$PROJECT" ]; then
  echo "--runtime-id and --project are required" >&2
  exit 2
fi

uv run python - "$RUNTIME_ID" "$PROJECT" "$OBJECT_PREFIX" <<'PY'
import sys
from pathlib import Path
from xray_runtime import GraphRuntimeManager, GraphRuntimeSpec

runtime_id, project, object_prefix = sys.argv[1:4]
spec = GraphRuntimeSpec(
    runtime_id=runtime_id,
    tenant_id="demo",
    bucket_name="xray-demo",
    graph_namespace="xray",
    graph_id="xray-demo",
    graph_database="xray",
    object_prefix=object_prefix,
    compose_project=project,
    bolt_port=17687,
    http_port=18443,
    admin_port=19090,
    indexer_admin_port=19091,
    minio_api_port=19000,
    minio_console_port=19001,
)
handle = GraphRuntimeManager(runtime_root=Path("infra/runtime")).prepare(spec)
print(handle.env_file)
PY

if [ "$CORE_ONLY" -eq 1 ]; then
  echo "Runtime prepared for core profile: $RUNTIME_ID"
fi
