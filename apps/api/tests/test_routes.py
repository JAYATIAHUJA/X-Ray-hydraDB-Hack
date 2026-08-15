from __future__ import annotations

from fastapi.testclient import TestClient
from xray_api import create_app


def client() -> TestClient:
    return TestClient(create_app())


def test_health_and_current_snapshot() -> None:
    api = client()

    assert api.get("/api/v1/health").json() == {"status": "ok"}
    snapshot = api.get("/api/v1/snapshots/current").json()

    assert snapshot["snapshot_id"] == "xray-demo-v1:fixture"
    assert snapshot["node_count"] == 17
    assert snapshot["edge_count"] == 29
    assert snapshot["evidence_count"] == 34


def test_ghosts_endpoint_returns_complete_fixture_finding() -> None:
    response = client().get("/api/v1/snapshots/xray-demo-v1:fixture/ghosts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_status"] == "complete"
    assert payload["findings"][0]["person_key"] == "person:maya-chen"
    assert "removal_impact" in payload["findings"][0]


def test_graph_endpoint_projects_person_communication_graph() -> None:
    response = client().get("/api/v1/snapshots/xray-demo-v1:fixture/graph")

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot_id"] == "xray-demo-v1:fixture"
    assert len(payload["nodes"]) == 10
    assert len(payload["edges"]) == 12
    maya = next(node for node in payload["nodes"] if node["key"] == "person:maya-chen")
    assert maya["selected"] is True
    assert maya["actual_size"] > maya["official_size"]
    assert payload["edges"][0]["strength"] in {"strong", "medium", "weak"}


def test_faultlines_endpoint_returns_no_path_coordination_debt() -> None:
    payload = client().get("/api/v1/snapshots/xray-demo-v1:fixture/faultlines").json()

    assert payload["analysis_status"] == "complete"
    assert payload["findings"][0]["source_module_key"] == "module:payments-api"
    assert payload["findings"][0]["tier"] == "no_path"


def test_gap_paths_endpoint_filters_requested_lineage() -> None:
    response = client().post(
        "/api/v1/snapshots/xray-demo-v1:fixture/gap-paths",
        json={
            "source_artifact_key": "artifact:code-change",
            "target_artifact_key": "artifact:directive",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_status"] == "complete"
    assert payload["findings"][0]["phantom_key"] == "artifact:missing-approval"
    assert "Absence does not establish deletion" in payload["status_explanation"]


def test_unknown_snapshot_returns_problem_detail() -> None:
    response = client().get("/api/v1/snapshots/missing/ghosts")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "snapshot_not_found"
