from __future__ import annotations

from xray_core.models import QuerySpec
from xray_core.ports import EndpointExpectation
from xray_hydra import HydraGateway, communication_paths_query, edge_upsert_batch


class FakeDriver:
    def __init__(self, responses: list[list[dict[str, object]]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append((query_, parameters_))
        return self.responses.pop(0)


def endpoint(index: int, canonical_key: str) -> EndpointExpectation:
    return EndpointExpectation(
        path_key=f"person:{index:020d}",
        hydra_id=index,
        canonical_key=canonical_key,
        dataset_id="xray-demo-v1",
    )


def resolved_row(expectation: EndpointExpectation) -> dict[str, object]:
    return {
        "id": expectation.hydra_id,
        "path_key": expectation.path_key,
        "canonical_key": expectation.canonical_key,
        "dataset_id": expectation.dataset_id,
    }


def test_run_batch_sends_rows_as_one_parameter() -> None:
    driver = FakeDriver([[{"count": 2}]])
    gateway = HydraGateway(driver)
    batch = edge_upsert_batch(
        "COMMUNICATES",
        (
            {
                "id": 7,
                "source_id": 1,
                "target_id": 2,
                "canonical_key": "communicates:a:b:aggregate",
                "dataset_id": "xray-demo-v1",
                "properties": "{}",
            },
            {
                "id": 8,
                "source_id": 2,
                "target_id": 3,
                "canonical_key": "communicates:b:c:aggregate",
                "dataset_id": "xray-demo-v1",
                "properties": "{}",
            },
        ),
    )

    assert gateway.run_batch(batch) == [{"count": 2}]
    assert driver.calls[0][1] == {"rows": [dict(row) for row in batch.rows]}


def test_paths_preflight_endpoints_and_filters_unrequested_cartesian_rows() -> None:
    alice = endpoint(1, "person:alice")
    bob = endpoint(2, "person:bob")
    carol = endpoint(3, "person:carol")
    driver = FakeDriver(
        [
            [resolved_row(alice)],
            [resolved_row(bob)],
            [resolved_row(carol)],
            [
                {
                    "path": {
                        "nodes": [
                            {"id": 1, "path_key": alice.path_key},
                            {"id": 2, "path_key": bob.path_key},
                        ]
                    },
                    "pathWeight": 1,
                    "pathCost": 1,
                },
                {
                    "path": {
                        "nodes": [
                            {"id": 1, "path_key": alice.path_key},
                            {"id": 3, "path_key": carol.path_key},
                        ]
                    },
                    "pathWeight": 1,
                    "pathCost": 1,
                },
            ],
        ]
    )
    query = communication_paths_query(
        [alice.path_key, bob.path_key],
        [alice.path_key, bob.path_key],
        max_len=4,
        path_count=3,
        result_limit=10,
        pairwise=True,
    )

    result = HydraGateway(driver).paths(
        query,
        requested_pairs={(alice.path_key, bob.path_key)},
        expected_endpoints={
            alice.path_key: alice,
            bob.path_key: bob,
            carol.path_key: carol,
        },
    )

    assert result.complete is True
    assert result.truncated is False
    assert len(result.paths) == 1
    assert result.paths[0].node_path_keys == (alice.path_key, bob.path_key)
    assert result.pair_evaluations[0].returned_rows == 1
    assert all("MATCH (n {path_key: $path_key})" in call[0] for call in driver.calls[:3])


def test_paths_with_unresolved_endpoint_do_not_execute_traversal() -> None:
    alice = endpoint(1, "person:alice")
    bob = endpoint(2, "person:bob")
    driver = FakeDriver([[resolved_row(alice)], []])
    query = QuerySpec(
        name="communication_paths",
        statement="CALL algo.MSpaths({}) YIELD path RETURN path",
        parameters={},
        max_len=4,
        result_limit=10,
    )

    result = HydraGateway(driver).paths(
        query,
        requested_pairs={(alice.path_key, bob.path_key)},
        expected_endpoints={alice.path_key: alice, bob.path_key: bob},
    )

    assert result.complete is False
    assert result.paths == ()
    assert len(driver.calls) == 2
    assert result.pair_evaluations[0].target_resolution.status == "missing"
