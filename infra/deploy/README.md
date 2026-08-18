# Deploying X-Ray

Two images, built from the repo root:

| Image | Dockerfile | Serves |
|---|---|---|
| `xray-api` | `apps/api/Dockerfile` | FastAPI on :8000, bundled Kafka snapshot (`XRAY_SNAPSHOT_DIR`), optional live HydraDB via `XRAY_HYDRA_URI` |
| `xray-web` | `apps/web/Dockerfile` | nginx on :8080 — landing `/`, dashboard `/app`, `/api/*` proxied same-origin to `API_UPSTREAM` |

## Local, one command

```bash
docker compose -f compose.demo.yaml up --build
# http://localhost:8080  ·  http://localhost:8080/app
```

## Fly.io (two apps, private network)

```bash
fly launch --no-deploy --copy-config --config infra/deploy/fly.api.toml --name xray-api
fly deploy  --config infra/deploy/fly.api.toml
fly launch --no-deploy --copy-config --config infra/deploy/fly.web.toml --name xray-web
fly deploy  --config infra/deploy/fly.web.toml
```

`API_UPSTREAM` in `fly.web.toml` points at `xray-api.internal:8000` (Fly's private DNS), so nothing about the API is public except through the web app's `/api` proxy.

## Railway / Render / any Docker host

Deploy both Dockerfiles; set `API_UPSTREAM` on the web service to the API's internal URL. If the frontend must call the API cross-origin instead, build the web image with `VITE_XRAY_API_BASE_URL=https://api.example.com` and set `XRAY_CORS_ORIGINS=https://web.example.com` on the API.

## Live engine in production

The images ship in **snapshot mode** — analytics run in-process on an ingested corpus, and every response header says so (`fallback`). To serve the live path, run the pinned HydraDB (`infra/runtime-images.lock`, `compose.yaml`) next to the API and set `XRAY_HYDRA_URI=bolt://…:7687` plus `XRAY_HYDRA_AUTH_TOKEN_FILE`. Nothing else changes; the same queries run against the engine.
