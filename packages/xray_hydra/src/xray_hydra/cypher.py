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


def cypher_string_literal(value: str) -> str:
    """Render a trusted scalar for HydraDB's literal-only property predicates."""
    if not value or any(ord(character) < 32 for character in value):
        raise CypherCompileError("Cypher string literals must be non-empty printable strings")
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _require_positive(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise CypherCompileError(f"{name} must be a positive integer")
    return value


def _validated_path_keys(values: Sequence[str]) -> tuple[str, ...]:
    if not values:
        raise CypherCompileError("path selectors must be non-empty canonical path keys")
    for value in values:
        if PATH_KEY.fullmatch(value) is None:
            raise CypherCompileError("path selectors must be non-empty canonical path keys")
    return tuple(values)


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
    source_values = _validated_path_keys(sources)
    target_values = _validated_path_keys(targets)
    source_values_literal = (
        "[" + ", ".join(cypher_string_literal(value) for value in source_values) + "]"
    )
    target_values_literal = (
        "[" + ", ".join(cypher_string_literal(value) for value in target_values) + "]"
    )
    statement = _one_statement(
        "CALL algo.MSpaths({"
        "sourceLabel: 'Person', "
        "sourceProperty: 'path_key', "
        f"sourceValues: {source_values_literal}, "
        "targetLabel: 'Person', "
        "targetProperty: 'path_key', "
        f"targetValues: {target_values_literal}, "
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
        f"sourceNode: {source_id}, "
        f"targetNode: {target_id}, "
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
        parameters={},
        max_len=max_len,
        result_limit=result_limit,
    )


def ontology_context_query(
    intent: str, dataset_id: str, subject_key: str, *, result_limit: int = 25
) -> QuerySpec:
    """Compile the exact graph read used to verify a Judge Mode answer."""
    if not dataset_id.strip() or not subject_key.strip():
        raise CypherCompileError("ontology context requires dataset and subject keys")
    _require_positive(result_limit, "result_limit")
    dataset_literal = cypher_string_literal(dataset_id)
    subject_literal = cypher_string_literal(subject_key)
    if intent == "owner":
        statement = _one_statement(
            f"MATCH (p:Person {{dataset_id: {dataset_literal}}})-[r:OWNS]->"
            f"(m:Module {{dataset_id: {dataset_literal}, canonical_key: {subject_literal}}}) "
            "RETURN p.canonical_key AS person_key, m.canonical_key AS subject_key, "
            "r.canonical_key AS relationship_key, r.properties AS properties "
            f"ORDER BY r.canonical_key LIMIT {result_limit}"
        )
    elif intent == "dependency_impact":
        statement = _one_statement(
            f"MATCH (dependent:Module {{dataset_id: {dataset_literal}}})-"
            f"[r:DEPENDS_ON]->(changed:Module {{dataset_id: {dataset_literal}, "
            f"canonical_key: {subject_literal}}}) "
            "RETURN dependent.canonical_key AS dependent_key, "
            "changed.canonical_key AS subject_key, r.canonical_key AS relationship_key, "
            f"r.properties AS properties ORDER BY r.canonical_key LIMIT {result_limit}"
        )
    elif intent == "approval":
        statement = _one_statement(
            f"MATCH (p:Phantom {{dataset_id: {dataset_literal}, "
            f"canonical_key: {subject_literal}}}) "
            "RETURN p.canonical_key AS subject_key, p.properties AS properties "
            f"LIMIT {result_limit}"
        )
    else:
        raise CypherCompileError(f"unsupported ontology intent {intent!r}")
    return QuerySpec(
        name=f"ontology_{intent}",
        statement=statement,
        parameters={},
        max_len=None,
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
    "cypher_string_literal",
    "edge_upsert_batch",
    "node_upsert_batch",
    "ontology_context_query",
    "sp_chain_query",
]
