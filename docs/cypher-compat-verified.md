# HydraDB Cypher compatibility notes

Status: scaffolded on 16 Aug 2026; live verification runs through
`tests/integration/test_hydradb_live.py` when `XRAY_HYDRA_URI` is set.

The compiler currently emits the conservative forms expected by the live probe:

- `algo.MSpaths` with `relDirection: 'BOTH'`
- `algo.SPpaths` with `relDirection: 'OUTGOING'`
- node and edge writes matched by integer `id`
- endpoint resolution by `path_key` only as a pre-query identity check, not as the traversal
  selector

The integration probe records which `relDirection` spellings parse on the pinned engine:
`both`, `BOTH`, `out`, `OUTGOING`, `in`, `incoming`, `INCOMING`.
