# HydraDB Cypher compatibility verified

Verified against the pinned HydraDB image on 16 Aug 2026:

- Image: `ghcr.io/hydra-db/hydradb@sha256:db78309a233be54662db29744047e985a39b51c45a270d1a1f47c31a62cdb709`
- Source commit: `02a40025d2d57e97ab2754c8256219cdbfeab379`
- Live test: `tests/integration/test_hydradb_live.py`

## Runtime configuration

- Local object storage requires a real MinIO image; the prior placeholder image cannot run.
- HydraDB requires `GRAPH_DATA_PATH`; `GRAPH_OBJECT_PREFIX` is not sufficient.
- The object-store layer requires bucket env aliases:
  - `AWS_BUCKET_NAME`
  - `AWS_BUCKET`
  - `AWS_REGION`

## Bolt execution

- HydraDB rejects explicit transactions.
- Use auto-commit `session.run(...)`, not Neo4j driver's `execute_query(...)`.

## Writes

Supported node batch shape:

```cypher
UNWIND $rows AS row
MERGE (n {id: row.id})
SET n:Person,
    n.properties = row.properties,
    n.path_key = row.path_key,
    n.canonical_key = row.canonical_key,
    n.dataset_id = row.dataset_id
```

Supported relationship batch shape:

```cypher
UNWIND $rows AS row
MATCH (s:Person {id: row.source_id}), (t:Person {id: row.target_id})
MERGE (s)-[r:COMMUNICATES {id: row.id}]->(t)
SET r.properties = row.properties,
    r.canonical_key = row.canonical_key,
    r.dataset_id = row.dataset_id
```

Relationship endpoint labels are required in the `MATCH`, so loader batches edges by
`(rel_type, source_label, target_label)`.

## Reads and algorithms

- Exact node reads by integer property work: `MATCH (n {id: $id})`.
- Exact string reads also parse, e.g. `dataset_id` + `canonical_key`, but traversal identity is resolved outside the engine.
- `collect(DISTINCT ...)` is not executable in this pinned Query engine.
- Untyped relationship patterns such as `-->()` are not supported; specify one relationship type.

`algo.MSpaths` verified shape:

```cypher
CALL algo.MSpaths({
  sourceLabel: 'Person',
  sourceProperty: 'path_key',
  sourceValues: ['person:00000000000000091001'],
  targetLabel: 'Person',
  targetProperty: 'path_key',
  targetValues: ['person:00000000000000091003'],
  relTypes: ['COMMUNICATES'],
  relDirection: 'BOTH',
  maxLen: 4,
  pathCount: 1,
  resultLimit: 10,
  pairwise: false
}) YIELD path, pathWeight, pathCost
RETURN path, pathWeight, pathCost
```

Notes:

- `sourceValues` / `targetValues` must be string lists. Integer `id` selector lists do not parse.
- Parsed `relDirection` values include `both`, `BOTH`, `OUTGOING`, `incoming`, and `INCOMING`.
- `out` and `in` do not parse.

`algo.SPpaths` verified shape:

```cypher
CALL algo.SPpaths({
  sourceNode: $source_id,
  targetNode: $target_id,
  relTypes: ['PRECEDED_BY'],
  relDirection: 'OUTGOING',
  maxLen: 8,
  resultLimit: 20
}) YIELD path, pathWeight, pathCost
RETURN path, pathWeight, pathCost
```

Notes:

- `sourceLabel` / `targetLabel` are only supported by `algo.MSpaths`.
- `sourceNode` / `targetNode` must be integer node ids.
- Path values are returned as alternating node/relationship entries, not as a `{"nodes": ...}` object.
