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

Seed the bundled fixture into live HydraDB with:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/hydra/seed-fixture
```

When `XRAY_HYDRA_URI` is unset, the seed endpoint returns `status = fallback` and does not
write anything.

## Source ingestion

X-Ray can now normalize deterministic exports from Slack, email, ticketing systems, and Git
before they enter the canonical evidence pipeline. The adapters intentionally require explicit
external IDs, recipients, reply authors, and module references; they do not infer those facts
from message text.

| Export | Adapter | Required fields |
| --- | --- | --- |
| Slack message | `slack_records` | `id`, `occurred_at_epoch`, `author_id` |
| Email | `email_records` | `id`, `occurred_at_epoch`, `from_id`, `to_ids` |
| Ticket | `ticket_records` | `id`, `occurred_at_epoch`, `reporter_id` |
| Git commit | `code_records` | `sha`, `occurred_at_epoch`, `author_id` |

All adapters also accept `module_keys` when the source has an explicit module reference.
Slack accepts resolved `parent_author_id` and `mentions`; email recipients become observed
communication inputs. Directory records for the referenced people and modules must be present
in the same canonical bundle before derived graph relationships are calculated.
