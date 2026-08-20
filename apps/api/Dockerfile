# X-Ray API — FastAPI + the analytics packages, uv-managed.
# Serves the bundled Kubernetes org demo snapshot by default (XRAY_SNAPSHOT_DIR); point
# XRAY_HYDRA_URI at a HydraDB Bolt endpoint to run the live engine path.
#
# Build from the repo root:  docker build -f apps/api/Dockerfile -t xray-api .
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app

# Workspace metadata first so the dependency layer caches.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY packages packages
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-workspace

# Sources stay at their repo-relative paths: the API resolves bundled fixtures
# via Path(__file__).parents[4] / "data" / "fixtures".
COPY apps/api/src apps/api/src
COPY data/fixtures data/fixtures
COPY data/snapshots/kubernetes-demo data/snapshots/kubernetes-demo
COPY data/snapshots/meshery-demo data/snapshots/meshery-demo
COPY data/snapshots/kafka-2025q2 data/snapshots/kafka-2025q2
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" XRAY_SNAPSHOT_DIR=/app/data/snapshots/kubernetes-demo PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).status==200 else 1)"
CMD ["sh", "-c", "uvicorn xray_api.app:app --host 0.0.0.0 --port ${PORT}"]
