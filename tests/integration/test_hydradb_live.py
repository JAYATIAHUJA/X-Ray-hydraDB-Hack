from __future__ import annotations

import os

import pytest
from xray_core.models import QuerySpec
from xray_hydra.cypher import (
    communication_paths_query,
    edge_upsert_batch,
    node_upsert_batch,
    sp_chain_query,
)
from xray_hydra.gateway import HydraGateway

pytestmark = pytest.mark.integration


def gateway() -> HydraGateway:
    uri = os.environ.get("XRAY_HYDRA_URI")
    if uri is None:
        pytest.skip("set XRAY_HYDRA_URI to run live HydraDB integration tests")
    try:
        from neo4j import GraphDatabase
    except ImportError:
        pytest.skip("neo4j driver is not installed")
    user = os.environ.get("XRAY_HYDRA_USER", "neo4j")
    password = os.environ.get("XRAY_HYDRA_PASSWORD", "password")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    return HydraGateway(driver)


def person_row(node_id: int, name: str) -> dict[str, object]:
    return {
        "id": node_id,
        "path_key": f"person:{node_id:020d}",
        "canonical_key": f"person:{name}",
        "dataset_id": "live-test",
        "properties": f'{{"name":"{name}"}}',
    }


def artifact_row(node_id: int, name: str) -> dict[str, object]:
    return {
        "id": node_id,
        "path_key": f"artifact:{node_id:020d}",
        "canonical_key": f"artifact:{name}",
        "dataset_id": "live-test",
        "properties": f'{{"name":"{name}"}}',
    }


def edge_row(edge_id: int, source_id: int, target_id: int, rel: str) -> dict[str, object]:
    return {
        "id": edge_id,
        "source_id": source_id,
        "target_id": target_id,
        "canonical_key": f"{rel.lower()}:{source_id}:{target_id}",
        "dataset_id": "live-test",
        "properties": '{"weight":1}',
    }


def test_live_hydradb_round_trip_and_path_algorithms() -> None:
    hydra = gateway()

    hydra.run_batch(
        node_upsert_batch(
            "Person",
            [person_row(91001, "a"), person_row(91002, "b"), person_row(91003, "c")],
        )
    )
    hydra.run_batch(
        edge_upsert_batch(
            "COMMUNICATES",
            [
                edge_row(92001, 91001, 91002, "communicates"),
                edge_row(92002, 91002, 91003, "communicates"),
            ],
            source_label="Person",
            target_label="Person",
        )
    )
    rows = hydra.run(
        communication_paths_query(
            ["person:00000000000000091001"],
            ["person:00000000000000091003"],
            max_len=4,
            path_count=1,
            result_limit=10,
            pairwise=False,
        )
    )
    assert len(rows) >= 1

    hydra.run_batch(
        node_upsert_batch(
            "Artifact",
            [artifact_row(93001, "artifact-a"), artifact_row(93002, "artifact-b")],
        )
    )
    hydra.run_batch(
        edge_upsert_batch(
            "PRECEDED_BY",
            [edge_row(94001, 93001, 93002, "preceded_by")],
            source_label="Artifact",
            target_label="Artifact",
        )
    )
    assert hydra.run(sp_chain_query(93001, 93002, max_len=8, result_limit=10))


def test_live_hydradb_cypher_compatibility_probe() -> None:
    hydra = gateway()
    parsed_directions: list[str] = []
    for direction in ["both", "BOTH", "out", "OUTGOING", "in", "incoming", "INCOMING"]:
        statement = (
            "CALL algo.MSpaths({sourceLabel: 'Person', "
            "sourceProperty: 'path_key', "
            "sourceValues: ['person:00000000000000091001'], "
            "targetLabel: 'Person', "
            "targetProperty: 'path_key', targetValues: ['person:00000000000000091002'], "
            "relTypes: ['COMMUNICATES'], "
            f"relDirection: '{direction}', maxLen: 1, pathCount: 1, resultLimit: 1, pairwise: false"
            "}) YIELD path, pathWeight, pathCost RETURN path, pathWeight, pathCost"
        )
        try:
            hydra.run(
                QuerySpec(
                    name="compat_rel_direction",
                    statement=statement,
                    parameters={},
                    max_len=1,
                    result_limit=1,
                )
            )
            parsed_directions.append(direction)
        except Exception:
            continue

    assert parsed_directions
    assert (
        hydra.run(
            QuerySpec(
                name="compat_string_match",
                statement=(
                    "MATCH (n:Person {dataset_id: 'live-test', canonical_key: 'person:a'}) "
                    "RETURN n.id AS id LIMIT 1"
                ),
                parameters={},
                max_len=None,
                result_limit=1,
            )
        )
        is not None
    )
    distinct_supported = True
    try:
        hydra.run(
            QuerySpec(
                name="compat_distinct",
                statement="MATCH (n) RETURN collect(DISTINCT n.id) AS ids LIMIT 1",
                parameters={},
                max_len=None,
                result_limit=1,
            )
        )
    except Exception:
        distinct_supported = False
    assert distinct_supported is False
