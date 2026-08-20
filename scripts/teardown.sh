#!/usr/bin/env sh
set -eu

RUNTIME_ID="runtime-demo"
REMOVE_VOLUMES=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --runtime-id) shift; RUNTIME_ID="$1" ;;
    --remove-volumes) REMOVE_VOLUMES=1 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

RUNTIME_DIR="infra/runtime/$RUNTIME_ID"
for name in api web; do
  pid_file="$RUNTIME_DIR/$name.pid"
  if [ -f "$pid_file" ]; then
    kill "$(cat "$pid_file")" 2>/dev/null || true
    rm -f "$pid_file"
  fi
done

if [ "$REMOVE_VOLUMES" -eq 1 ]; then
  uv run python -m xray_runtime.manager stop --runtime-id "$RUNTIME_ID" --remove-volumes
else
  uv run python -m xray_runtime.manager stop --runtime-id "$RUNTIME_ID"
fi
