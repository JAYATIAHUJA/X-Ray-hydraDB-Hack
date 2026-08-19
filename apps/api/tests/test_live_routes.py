"""HTTP-level tests for the HydraDB-backed lens paths.

These exercise the real FastAPI routes with the ``get_settings`` / ``get_gateway``
dependencies overridden, so the live branches (MSpaths / SPpaths / scoped reads)
run end-to-end through the app rather than being called as bare functions.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from xray_api import create_app
from xray_api.config import XraySettings, get_settings
from xray_api.dependencies import get_gateway
from xray_hydra import HydraGateway

LIVE_SETTINGS = XraySettings(hydra_uri="bolt://hydra.example:7687", hydra_database="xray")
SNAPSHOT = "xray-demo-v1:fixture"


class ScriptedDriver:
    """Route each statement to a canned response by substring, recording every call."""

    def __init__(self, routes: list[tuple[str, list[dict[str, object]]]]) -> None:
        self.routes = routes
        self.statements: list[str] = []
        self.parameters: list[dict[str, object] | None] = []

    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.statements.append(query_)
        self.parameters.append(parameters_)
        for needle, rows in self.routes:
            if needle in query_:
                return rows
        return []


class FailingDriver:
    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        raise RuntimeError("engine unavailable mid-request")


def _client(driver: object) -> TestClient:
    app = create_app()
    gateway = HydraGateway(driver)  # type: ignore[arg-type]

    def _gateway() -> Iterator[HydraGateway | None]:
        yield gateway

    app.dependency_overrides[get_settings] = lambda: LIVE_SETTINGS
    app.dependency_overrides[get_gateway] = _gateway
    return TestClient(app)


def _path(*keys: str) -> dict[str, object]:
    return {
        "path": {"nodes": [{"canonical_key": key} for key in keys]},
        "pathWeight": 1,
        "pathCost": len(keys) - 1,
    }


def test_ghosts_route_runs_one_mspaths_call_and_reports_hydradb_source() -> None:
    driver = ScriptedDriver(
        [
            (
                "algo.MSpaths",
                [
                    _path("person:alex-rivera", "person:maya-chen", "person:sam-wu"),
                    _path("person:priya-shah", "person:maya-chen", "person:omar-haddad"),
                ],
            )
        ]
    )

    response = _client(driver).get(f"/api/v1/snapshots/{SNAPSHOT}/ghosts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "hydradb"
    assert payload["analysis_status"] == "complete"
    assert payload["degraded_reason"] is None
    executed = payload["executed_query"]
    assert executed["round_trips"] == 1
    assert "CALL algo.MSpaths" in executed["text"]
    assert "sourceLabel: 'Person'" in executed["text"]
    assert executed["max_len"] == 4
    assert [s for s in driver.statements if "algo.MSpaths" in s] == [executed["text"]]
    top = payload["findings"][0]
    assert top["person_key"] == "person:maya-chen"
    assert top["sampled_centrality"] > 0
    assert top["centrality_method"] == "exact_undirected_networkx"
    assert top["removal_impact"] is not None


def test_faultlines_route_batches_owner_pairs_into_one_call_and_tiers_correctly() -> None:
    # Owners on the demo faultline are alex-rivera and theo-brooks. Return a 3-hop
    # path between them so the live tier becomes weak_coordination, not no_path.
    driver = ScriptedDriver(
        [
            (
                "algo.MSpaths",
                [
                    _path(
                        "person:theo-brooks",
                        "person:maya-chen",
                        "person:sam-wu",
                        "person:alex-rivera",
                    )
                ],
            )
        ]
    )

    response = _client(driver).get(f"/api/v1/snapshots/{SNAPSHOT}/faultlines")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "hydradb"
    assert payload["analysis_status"] == "complete"
    assert payload["executed_query"]["round_trips"] == 1
    assert sum("algo.MSpaths" in s for s in driver.statements) == 1
    finding = payload["findings"][0]
    assert {finding["source_owner_key"], finding["target_owner_key"]} == {
        "person:alex-rivera",
        "person:theo-brooks",
    }
    assert finding["communication_distance"] == 3
    assert finding["tier"] == "weak_coordination"


def test_faultlines_route_uses_reversed_pair_lookup_without_fabricating_no_path() -> None:
    # A direct 1-hop path in the *reverse* owner order must still be recognised
    # (regression for the sorted-vs-unsorted lookup bug) and must yield no finding.
    driver = ScriptedDriver([("algo.MSpaths", [_path("person:theo-brooks", "person:alex-rivera")])])

    payload = _client(driver).get(f"/api/v1/snapshots/{SNAPSHOT}/faultlines").json()

    assert payload["source"] == "hydradb"
    assert payload["findings"] == []


def test_gap_paths_route_runs_sppaths_and_returns_the_chain() -> None:
    driver = ScriptedDriver(
        [
            (
                "algo.SPpaths",
                [_path("artifact:code-change", "artifact:missing-approval", "artifact:directive")],
            ),
            (
                "MATCH (phantom:Phantom {dataset_id: $dataset_id}) RETURN",
                [
                    {
                        "phantom_key": "artifact:missing-approval",
                        "phantom_id": 6766613005167498529,
                        "properties": (
                            '{"expected_kind":"approval",'
                            '"reason":"required_sequence_step_missing",'
                            '"inferred_epoch":1736003600}'
                        ),
                    }
                ],
            ),
            (
                "MATCH (phantom:Phantom {dataset_id: $dataset_id})-[r:PRECEDED_BY]",
                [
                    {
                        "phantom_key": "artifact:missing-approval",
                        "artifact_key": "artifact:directive",
                    }
                ],
            ),
            (
                "-[r:PRECEDED_BY]->(phantom:Phantom",
                [
                    {
                        "phantom_key": "artifact:missing-approval",
                        "artifact_key": "artifact:code-change",
                    }
                ],
            ),
        ]
    )

    response = _client(driver).post(
        f"/api/v1/snapshots/{SNAPSHOT}/gap-paths",
        json={
            "source_artifact_key": "artifact:code-change",
            "target_artifact_key": "artifact:directive",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "hydradb"
    executed = payload["executed_query"]
    assert "CALL algo.SPpaths" in executed["text"]
    assert executed["max_len"] == 8
    finding = payload["findings"][0]
    assert finding["phantom_key"] == "artifact:missing-approval"
    assert finding["chain"]["node_keys"] == [
        "artifact:code-change",
        "artifact:missing-approval",
        "artifact:directive",
    ]
    assert finding["chain"]["phantom_indices"] == [1]
    for params in driver.parameters:
        if params and "dataset_id" in params:
            assert params["dataset_id"] == "xray-demo-v1"


@pytest.mark.parametrize("route", ["ghosts", "faultlines"])
def test_lens_routes_degrade_honestly_when_engine_fails_mid_request(route: str) -> None:
    response = _client(FailingDriver()).get(f"/api/v1/snapshots/{SNAPSHOT}/{route}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_status"] == "partial"
    assert payload["degraded_reason"] is not None
    assert "engine unavailable" in payload["degraded_reason"]
    assert payload["executed_query"] is not None
    # Fixture findings are still served so the UI has something to render.
    assert payload["findings"]


def test_graph_route_scopes_live_reads_by_dataset_and_limit() -> None:
    driver = ScriptedDriver(
        [
            (
                "MATCH (p:Person {dataset_id: $dataset_id})",
                [
                    {
                        "id": 8735786581004019202,
                        "key": "person:maya-chen",
                        "properties": (
                            '{"display_name":"Maya Chen","role_rank":1,"team_id":"team:payments"}'
                        ),
                    }
                ],
            ),
            ("[r:COMMUNICATES]", []),
        ]
    )

    payload = _client(driver).get(f"/api/v1/snapshots/{SNAPSHOT}/graph").json()

    assert [node["key"] for node in payload["nodes"]] == ["person:maya-chen"]
    scoped = [p for p in driver.parameters if p and "dataset_id" in p]
    assert scoped and all(p["dataset_id"] == "xray-demo-v1" and "limit" in p for p in scoped)
    assert all("LIMIT $limit" in s for s in driver.statements if "MATCH (p:Person" in s)


def test_ghosts_route_what_if_recomputes_graph_without_removed_person() -> None:
    driver = ScriptedDriver(
        [
            (
                "algo.MSpaths",
                [
                    _path("person:alex-rivera", "person:maya-chen", "person:sam-wu"),
                    _path("person:priya-shah", "person:maya-chen", "person:omar-haddad"),
                    _path("person:alex-rivera", "person:priya-shah"),
                ],
            )
        ]
    )

    payload = (
        _client(driver)
        .get(f"/api/v1/snapshots/{SNAPSHOT}/ghosts", params={"exclude": ["person:maya-chen"]})
        .json()
    )

    assert payload["source"] == "hydradb"
    what_if = payload["what_if"]
    assert what_if["excluded_person_keys"] == ["person:maya-chen"]
    assert what_if["sampled_pairs_before"] > what_if["sampled_pairs_after"]
    assert what_if["pairs_lost"] == (
        what_if["sampled_pairs_before"] - what_if["sampled_pairs_after"]
    )
    assert what_if["max_len"] == 4
    comparison = payload["comparison"]
    assert comparison["engine_round_trips"] == 1
    assert comparison["client_equivalent_round_trips"] == 45  # 10 people -> C(10, 2)
    assert comparison["client_ms"] >= 0
    assert comparison["engine_ms"] is not None
    assert all(f["person_key"] != "person:maya-chen" for f in payload["findings"])


def test_ghosts_route_rejects_unknown_exclusion() -> None:
    response = _client(ScriptedDriver([])).get(
        f"/api/v1/snapshots/{SNAPSHOT}/ghosts", params={"exclude": ["person:nobody"]}
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "person_not_found"
