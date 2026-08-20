from __future__ import annotations

import pytest
from xray_hydra.cypher import (
    CypherCompileError,
    communication_paths_query,
    edge_upsert_batch,
    node_upsert_batch,
    ontology_context_query,
    sp_chain_query,
)


def test_ontology_context_queries_are_typed_and_parameterized() -> None:
    owner = ontology_context_query("owner", "demo", "module:payments-api")
    impact = ontology_context_query("dependency_impact", "demo", "module:ledger-worker")
    approval = ontology_context_query("approval", "demo", "artifact:missing-approval")

    assert "[r:OWNS]" in owner.statement
    assert "[r:DEPENDS_ON]" in impact.statement
    assert "p:Phantom" in approval.statement
    assert "$subject_key" in owner.statement
    assert owner.parameters["subject_key"] == "module:payments-api"
    assert ";" not in owner.statement


def test_communication_paths_use_equal_pairwise_sets_and_only_communication() -> None:
    keys = [
        "person:00000000000000000001",
        "person:00000000000000000002",
    ]
    spec = communication_paths_query(
        keys,
        keys,
        max_len=4,
        path_count=3,
        result_limit=100,
        pairwise=True,
    )

    assert "sourceLabel: 'Person'" in spec.statement
    assert "sourceProperty: 'path_key'" in spec.statement
    assert "sourceValues: $source_values" in spec.statement
    assert "targetLabel: 'Person'" in spec.statement
    assert "targetValues: $target_values" in spec.statement
    assert "relTypes: ['COMMUNICATES']" in spec.statement
    assert "relDirection: 'BOTH'" in spec.statement
    assert "resultLimit: 100" in spec.statement
    assert "RETURN path, pathWeight, pathCost" in spec.statement
    assert "collect(" not in spec.statement
    assert spec.max_len == 4
    assert spec.result_limit == 100
    assert spec.parameters == {
        "source_values": tuple(keys),
        "target_values": tuple(keys),
    }


def test_cross_set_communication_paths_disable_pairwise() -> None:
    spec = communication_paths_query(
        ["person:00000000000000000001"],
        ["person:00000000000000000002"],
        max_len=4,
        path_count=3,
        result_limit=100,
        pairwise=False,
    )

    assert "pairwise: false" in spec.statement
    assert "relTypes: ['COMMUNICATES']" in spec.statement


def test_pairwise_rejects_unequal_selector_sets() -> None:
    with pytest.raises(CypherCompileError, match="equal selector sets"):
        communication_paths_query(
            ["person:00000000000000000001"],
            ["person:00000000000000000002"],
            max_len=4,
            path_count=3,
            result_limit=100,
            pairwise=True,
        )


@pytest.mark.parametrize(
    "sources,targets,max_len,path_count,result_limit",
    [
        ([], ["person:00000000000000000001"], 4, 3, 100),
        (["person:alice"], ["person:00000000000000000001"], 4, 3, 100),
        (["person:00000000000000000001"], ["person:00000000000000000002"], 5, 3, 100),
        (["person:00000000000000000001"], ["person:00000000000000000002"], 4, 0, 100),
        (["person:00000000000000000001"], ["person:00000000000000000002"], 4, 3, 0),
    ],
)
def test_communication_paths_reject_invalid_inputs(
    sources: list[str],
    targets: list[str],
    max_len: int,
    path_count: int,
    result_limit: int,
) -> None:
    with pytest.raises(CypherCompileError):
        communication_paths_query(
            sources,
            targets,
            max_len=max_len,
            path_count=path_count,
            result_limit=result_limit,
            pairwise=False,
        )


def test_sp_chain_hard_codes_preceded_by_and_binds_ids() -> None:
    spec = sp_chain_query(1, 2, max_len=8, result_limit=20)

    assert "relTypes: ['PRECEDED_BY']" in spec.statement
    assert "sourceNode: $source_id" in spec.statement
    assert "targetNode: $target_id" in spec.statement
    assert spec.parameters == {"source_id": 1, "target_id": 2}
    assert spec.max_len == 8
    assert spec.result_limit == 20


@pytest.mark.parametrize(
    "source_id,target_id,max_len,result_limit",
    [(0, 2, 8, 20), (1, 0, 8, 20), (1, 2, 9, 20), (1, 2, 8, 0)],
)
def test_sp_chain_rejects_invalid_bounds(
    source_id: int, target_id: int, max_len: int, result_limit: int
) -> None:
    with pytest.raises(CypherCompileError):
        sp_chain_query(source_id, target_id, max_len=max_len, result_limit=result_limit)


def test_write_batches_keep_rows_as_one_parameter_and_one_statement() -> None:
    rows = (
        {
            "id": 1,
            "path_key": "person:00000000000000000001",
            "canonical_key": "person:alice",
            "dataset_id": "xray-demo-v1",
            "properties": "{}",
        },
        {
            "id": 2,
            "path_key": "person:00000000000000000002",
            "canonical_key": "person:bob",
            "dataset_id": "xray-demo-v1",
            "properties": "{}",
        },
    )
    spec = node_upsert_batch("Person", rows)

    assert "$rows" in spec.statement
    assert spec.statement.count("UNWIND") == 1
    assert ";" not in spec.statement
    assert spec.rows == rows


def test_write_batches_reject_unknown_labels_rel_types_and_nonprimitive_values() -> None:
    with pytest.raises(CypherCompileError):
        node_upsert_batch("BadLabel", ())
    with pytest.raises(CypherCompileError):
        edge_upsert_batch("BAD_REL", (), source_label="Person", target_label="Person")
    with pytest.raises(CypherCompileError):
        edge_upsert_batch("COMMUNICATES", (), source_label="BadLabel", target_label="Person")
    with pytest.raises(ValueError, match="int, float, bool, or string"):
        node_upsert_batch("Person", ({"id": 1, "nested": {"bad": "value"}},))


def test_edge_batch_renders_allow_listed_relationship() -> None:
    spec = edge_upsert_batch(
        "COMMUNICATES",
        (
            {
                "id": 7,
                "source_id": 1,
                "target_id": 2,
                "canonical_key": "communicates:alice:bob:aggregate",
                "dataset_id": "xray-demo-v1",
                "properties": "{}",
            },
        ),
        source_label="Person",
        target_label="Person",
    )

    assert "MATCH (s:Person {id: row.source_id}), (t:Person {id: row.target_id})" in spec.statement
    assert "MERGE (s)-[r:COMMUNICATES {id: row.id}]->(t)" in spec.statement
    assert "$rows" in spec.statement


@pytest.mark.parametrize("rel_type", ["REPLIES_TO", "EXPECTED_BEFORE"])
def test_edge_batch_accepts_gap_relationships_emitted_by_ingest(rel_type: str) -> None:
    spec = edge_upsert_batch(
        rel_type,
        (
            {
                "id": 7,
                "source_id": 1,
                "target_id": 2,
                "canonical_key": f"{rel_type.lower()}:a:b",
                "dataset_id": "xray-demo-v1",
                "properties": "{}",
            },
        ),
        source_label="Artifact",
        target_label="Phantom",
    )

    assert f"MERGE (s)-[r:{rel_type} {{id: row.id}}]->(t)" in spec.statement
    assert "s:Artifact" in spec.statement
    assert "t:Phantom" in spec.statement
