# X-Ray-hydraDB-Hack

## HydraDB connection

The API runs in fixture fallback mode unless a live HydraDB/Neo4j endpoint is configured.

Set these environment variables before starting `xray_api.app`:

```powershell
$env:XRAY_HYDRA_URI = "bolt://localhost:7687"
$env:XRAY_HYDRA_USER = "neo4j"
$env:XRAY_HYDRA_PASSWORD = "password"
$env:XRAY_HYDRA_DATABASE = "neo4j"
```

`GET /api/v1/health` reports:

- `hydra.status = fallback` when no live URI is configured.
- `hydra.status = live` when the API can ping HydraDB.
- `hydra.status = offline` when a URI is configured but the ping fails.
