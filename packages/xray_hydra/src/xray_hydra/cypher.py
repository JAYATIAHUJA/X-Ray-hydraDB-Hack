from __future__ import annotations

import re
from collections.abc import Sequence

from xray_core.models import QuerySpec, Scalar, WriteBatchSpec

PATH_KEY = re.compile(r"^[a-z]+:[0-9]{20}$")

NODE_LABELS = frozenset({"Person", "Team", "Artifact", "Module", "Phantom"})
RELATION_TYPES = frozenset(
    {
        "REPORTS_TO",
        "AUTHORED",
        "MENTIONS",
        "COMMUNICATES",
        "ABOUT",
        "OWNS",
        "DEPENDS_ON",
        "PRECEDED_BY",
        "REPLIES_TO",
        "EXPECTED_BEFORE",
    }
)
PEOPLE_MAX_LEN = 4
CHAIN_MAX_LEN = 8
REL_DIRECTION_BOTH = "BOTH"
REL_DIRECTION_OUT = "OUTGOING"


class CypherCompileError(ValueError):
    """Raised when a query cannot be rendered inside the allow-listed compiler."""


def _require_positive(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise CypherCompileError(f"{name} must be a positive integer")
    return value


def _literal_list(values: Sequence[str]) -> str:
    if not values:
        raise CypherCompileError("path selectors must be non-empty canonical path keys")
    rendered: list[str] = []
    for value in values:
        if PATH_KEY.fullmatch(value) is None:
            raise CypherCompileError("path selectors must be non-empty canonical path keys")
        rendered.append(f"'{value}'")
    return "[" + ", ".join(rendered) + "]"


def _one_statement(statement: str) -> str:
    normalized = statement.strip()
    if normalized.endswith(";"):
        normalized = normalized[:-1].rstrip()
    if ";" in normalized:
        raise CypherCompileError("compiled Cypher must contain exactly one statement")
    return normalized


def _require_label(label: str) -> str:
    if label not in NODE_LABELS:
        raise CypherCompileError(f"unsupported node label {label!r}")
    return label


def _require_rel_type(rel_type: str) -> str:
    if rel_type not in RELATION_TYPES:
        raise CypherCompileError(f"unsupported relationship type {rel_type!r}")
    return rel_type


def communication_paths_query(
    sources: Sequence[str],
    targets: Sequence[str],
    *,
    max_len: int,
    path_count: int,
    result_limit: int,
    pairwise: bool,
) -> QuerySpec:
    if pairwise and tuple(sources) != tuple(targets):
        raise CypherCompileError("pairwise communication paths require equal selector sets")
    if _require_positive(max_len, "max_len") > PEOPLE_MAX_LEN:
        raise CypherCompileError("communication max_len cannot exceed 4")
    _require_positive(path_count, "path_count")
    _require_positive(result_limit, "result_limit")
    pairwise_literal = "true" if pairwise else "false"
    statement = _one_statement(
        "CALL algo.MSpaths({"
        "sourceLabel: 'Person', "
        "sourceProperty: 'path_key', "
        f"sourceValues: {_literal_list(sources)}, "
        "targetLabel: 'Person', "
        "targetProperty: 'path_key', "
        f"targetValues: {_literal_list(targets)}, "
        "relTypes: ['COMMUNICATES'], "
        f"relDirection: '{REL_DIRECTION_BOTH}', "
        f"maxLen: {max_len}, "
        f"pathCount: {path_count}, "
        f"resultLimit: {result_limit}, "
        f"pairwise: {pairwise_literal}"
        "}) YIELD path, pathWeight, pathCost "
        "RETURN path, pathWeight, pathCost"
    )
    return QuerySpec(
        name="communication_paths",
        statement=statement,
        parameters={},
        max_len=max_len,
        result_limit=result_limit,
    )


def sp_chain_query(
    source_id: int, target_id: int, *, max_len: int = 8, result_limit: int = 20
) -> QuerySpec:
    _require_positive(source_id, "source_id")
    _require_positive(target_id, "target_id")
    if _require_positive(max_len, "max_len") > CHAIN_MAX_LEN:
        raise CypherCompileError("chain max_len cannot exceed 8")
    _require_positive(result_limit, "result_limit")
    statement = _one_statement(
        "CALL algo.SPpaths({"
        "sourceNode: $source_id, "
        "targetNode: $target_id, "
        "relTypes: ['PRECEDED_BY'], "
        f"relDirection: '{REL_DIRECTION_OUT}', "
        f"maxLen: {max_len}, "
        f"resultLimit: {result_limit}"
        "}) YIELD path, pathWeight, pathCost "
        "RETURN path, pathWeight, pathCost"
    )
    return QuerySpec(
        name="sp_chain",
        statement=statement,
        parameters={"source_id": source_id, "target_id": target_id},
        max_len=max_len,
        result_limit=result_limit,
    )


def node_upsert_batch(label: str, rows: Sequence[dict[str, Scalar]]) -> WriteBatchSpec:
    safe_label = _require_label(label)
    statement = _one_statement(
        "UNWIND $rows AS row MERGE (n {id: row.id}) "
        f"SET n:{safe_label}, "
        "n.properties = row.properties, "
        "n.path_key = row.path_key, "
        "n.canonical_key = row.canonical_key, "
        "n.dataset_id = row.dataset_id"
    )
    return WriteBatchSpec(name=f"upsert_nodes_{safe_label}", statement=statement, rows=tuple(rows))


def edge_upsert_batch(
    rel_type: str,
    rows: Sequence[dict[str, Scalar]],
    *,
    source_label: str,
    target_label: str,
) -> WriteBatchSpec:
    safe_rel_type = _require_rel_type(rel_type)
    safe_source_label = _require_label(source_label)
    safe_target_label = _require_label(target_label)
    statement = _one_statement(
        "UNWIND $rows AS row "
        f"MATCH (s:{safe_source_label} {{id: row.source_id}}), "
        f"(t:{safe_target_label} {{id: row.target_id}}) "
        f"MERGE (s)-[r:{safe_rel_type} {{id: row.id}}]->(t) "
        "SET r.properties = row.properties, "
        "r.canonical_key = row.canonical_key, "
        "r.dataset_id = row.dataset_id"
    )
    return WriteBatchSpec(
        name=f"upsert_edges_{safe_rel_type}_{safe_source_label}_{safe_target_label}",
        statement=statement,
        rows=tuple(rows),
    )


__all__ = [
    "CypherCompileError",
    "communication_paths_query",
    "edge_upsert_batch",
    "node_upsert_batch",
    "sp_chain_query",
]
