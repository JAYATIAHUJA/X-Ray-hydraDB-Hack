from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from xray_api import create_app
from xray_api.config import settings_from_env
from xray_api.dependencies import demo_bundle
from xray_api.hydra import communication_distances, gap_rows, graph_rows, seed_bundle
from xray_api.lenses import live_gap_chain, live_ghost_findings
from xray_core.models import CanonicalBundle, LoadReport, SnapshotManifest, WriteBatchSpec
from xray_hydra import HydraGateway


def client() -> TestClient:
    return TestClient(create_app())


def test_health_and_current_snapshot() -> None:
    api = client()

    health = api.get("/api/v1/health").json()
    assert health["status"] == "ok"
    assert health["hydra"]["status"] == "fallback"
    assert health["hydra"]["configured"] is False
    snapshot = api.get("/api/v1/snapshots/current").json()

    assert snapshot["snapshot_id"] == "xray-demo-v1:fixture"
    assert snapshot["node_count"] == 17
    assert snapshot["edge_count"] == 30
    assert snapshot["evidence_count"] == 34


def test_settings_reads_hydradb_environment_contract() -> None:
    settings = settings_from_env(
        {
            "XRAY_HYDRA_URI": "bolt://localhost:7687",
            "XRAY_HYDRA_USER": "neo4j",
            "XRAY_HYDRA_PASSWORD": "password",
            "XRAY_HYDRA_DATABASE": "xray",
        }
    )

    assert settings.hydra_configured is True
    assert settings.hydra_uri == "bolt://localhost:7687"
    assert settings.hydra_user == "neo4j"
    assert settings.hydra_password == "password"
    assert settings.hydra_database == "xray"


def test_seed_fixture_endpoint_skips_without_hydradb_config() -> None:
    response = client().post("/api/v1/hydra/seed-fixture")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "fallback"
    assert payload["hydra"]["configured"] is False
    assert payload["report"] is None


def test_seed_bundle_loads_fixture_with_gateway(tmp_path: Path) -> None:
    driver = RecordingDriver()
    settings = settings_from_env({"XRAY_HYDRA_URI": "bolt://hydra.example:7687"})

    result = seed_bundle(
        settings,
        demo_bundle(),
        gateway=HydraGateway(driver),
        loader_factory=lambda gateway: RecordingLoader(gateway),
        snapshot_dir=tmp_path / "seed-bundle-loads-fixture",
        snapshot_writer=recording_snapshot_writer,
    )

    assert result.status == "complete"
    assert result.report is not None
    assert result.report.node_count == 17
    assert result.report.edge_count == 29
    assert result.report.failed_batches == ()
    assert len(driver.statements) > 0


def test_ghosts_endpoint_returns_complete_fixture_finding() -> None:
    response = client().get("/api/v1/snapshots/xray-demo-v1:fixture/ghosts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_status"] == "complete"
    assert payload["findings"][0]["person_key"] == "person:maya-chen"
    assert "removal_impact" in payload["findings"][0]
    assert payload["findings"][0]["evidence"][0]["content_sha256"]
    assert payload["findings"][0]["evidence"][0]["confidence"] == 100


class RecordingDriver:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, object] | None = None,
    ) -> list[dict[str, int]]:
        self.statements.append(query_)
        rows = parameters_["rows"] if parameters_ is not None and "rows" in parameters_ else []
        return [{"count": len(rows) if isinstance(rows, list) else 0}]


class RecordingLoader:
    def __init__(self, gateway: HydraGateway) -> None:
        self.gateway = gateway

    def load(
        self,
        snapshot_dir: object,
        manifest: SnapshotManifest,
    ) -> LoadReport:
        self.gateway.run_batch(
            WriteBatchSpec(
                name="test_seed_batch",
                statement="RETURN 1",
                rows=(),
            )
        )
        return LoadReport(
            snapshot_id=manifest.snapshot_id,
            node_count=17,
            edge_count=29,
            attempted_batches=3,
            completed_batches=3,
            resumed_batches=0,
            failed_batches=(),
            graph_fingerprint="abc123",
            verification_queries=(),
        )


def recording_snapshot_writer(bundle: CanonicalBundle, snapshot_dir: object) -> SnapshotManifest:
    return SnapshotManifest(
        snapshot_id=f"{bundle.dataset_id}:test",
        dataset_id=bundle.dataset_id,
        schema_version="1.0.0",
        content_sha256="0" * 64,
        row_counts={
            "nodes": len(bundle.nodes),
            "edges": len(bundle.edges),
            "evidence": len(bundle.evidence),
        },
        file_sha256={"nodes.parquet": "1" * 64},
    )


class GraphRowsDriver:
    def __init__(self) -> None:
        self.parameters: list[dict[str, object] | None] = []

    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.parameters.append(parameters_)
        if "MATCH (p:Person" in query_:
            return [
                {
                    "id": 5217034559407717516,
                    "key": "person:alex-rivera",
                    "properties": (
                        '{"display_name":"Alex Rivera","role_rank":4,"team_id":"team:payments"}'
                    ),
                }
            ]
        return [
            {
                "source_id": 5217034559407717516,
                "target_id": 8735786581004019202,
                "source": "person:alex-rivera",
                "target": "person:maya-chen",
                "properties": '{"weight":5}',
            }
        ]


class DistanceDriver:
    def __init__(self) -> None:
        self.parameters: list[dict[str, object] | None] = []

    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.parameters.append(parameters_)
        return [
            {
                "path": {
                    "nodes": [
                        {"canonical_key": "person:alex-rivera"},
                        {"canonical_key": "person:maya-chen"},
                    ]
                },
                "pathWeight": 1,
                "pathCost": 1,
            }
        ]


class GapRowsDriver:
    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        if "AS artifact_key" in query_:
            if "REPLIES_TO" in query_:
                return []
            if (
                "phantom:Phantom" in query_
                and "artifact:Artifact" in query_
                and query_.index("phantom:Phantom") < query_.index("artifact:Artifact")
            ):
                return [
                    {
                        "phantom_key": "artifact:missing-approval",
                        "artifact_key": "artifact:directive",
                    }
                ]
            return [
                {
                    "phantom_key": "artifact:missing-approval",
                    "artifact_key": "artifact:code-change",
                }
            ]
        return [
            {
                "phantom_key": "artifact:missing-approval",
                "phantom_id": 6766613005167498529,
                "properties": (
                    '{"expected_kind":"approval","reason":"required_sequence_step_missing",'
                    '"inferred_epoch":1736003600}'
                ),
                "predecessor_keys": ["artifact:directive"],
                "successor_keys": ["artifact:code-change"],
            }
        ]


class GhostPathsDriver:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.parameters: list[dict[str, object] | None] = []

    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.statements.append(query_)
        self.parameters.append(parameters_)
        return [
            {
                "path": {
                    "nodes": [
                        {"canonical_key": "person:alex-rivera"},
                        {"canonical_key": "person:maya-chen"},
                        {"canonical_key": "person:sam-wu"},
                    ]
                },
                "pathWeight": 1,
                "pathCost": 1,
            }
        ]


class GapChainDriver:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.parameters: list[dict[str, object] | None] = []

    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.statements.append(query_)
        self.parameters.append(parameters_)
        return [
            {
                "path": {
                    "nodes": [
                        {"canonical_key": "artifact:code-change"},
                        {"canonical_key": "artifact:missing-approval"},
                        {"canonical_key": "artifact:directive"},
                    ]
                },
                "pathWeight": 1,
                "pathCost": 1,
            }
        ]


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


def test_graph_rows_reads_live_hydradb_projection() -> None:
    settings = settings_from_env({"XRAY_HYDRA_URI": "bolt://hydra.example:7687"})
    driver = GraphRowsDriver()

    rows = graph_rows(settings, demo_bundle(), gateway=HydraGateway(driver))

    assert rows is not None
    assert rows.nodes[0].key == "person:alex-rivera"
    assert rows.nodes[0].properties["display_name"] == "Alex Rivera"
    assert rows.edges[0].source == "person:alex-rivera"
    assert rows.edges[0].target == "person:maya-chen"
    assert rows.edges[0].weight == 5.0
    assert driver.parameters == [
        {"dataset_id": "xray-demo-v1", "limit": 10},
        {"dataset_id": "xray-demo-v1", "limit": 30},
    ]


def test_communication_distances_reads_live_hydradb_paths() -> None:
    settings = settings_from_env({"XRAY_HYDRA_URI": "bolt://hydra.example:7687"})
    driver = DistanceDriver()

    result = communication_distances(
        settings,
        demo_bundle(),
        (("person:alex-rivera", "person:maya-chen"),),
        gateway=HydraGateway(driver),
    )

    assert result is not None
    assert result.error is None
    assert result.distances == {("person:alex-rivera", "person:maya-chen"): 1}
    assert result.query.name == "communication_paths"
    assert "sourceProperty: 'path_key'" in result.query.statement
    assert "sourceLabel: 'Person'" in result.query.statement
    assert "canonical_key" not in result.query.statement
    assert driver.parameters == [{}]


def test_faultline_live_distance_lookup_accepts_reversed_owner_pair() -> None:
    from xray_analytics import FaultlineFinding
    from xray_api.app import _with_live_distance

    finding = FaultlineFinding(
        source_module_key="module:a",
        target_module_key="module:b",
        source_owner_key="person:z",
        target_owner_key="person:a",
        dependency_weight=10,
        source_owner_confidence=90,
        target_owner_confidence=90,
        communication_distance=None,
        tier="no_path",
        severity=10.0,
    )

    scored = _with_live_distance(finding, {("person:a", "person:z"): 2})

    assert scored.communication_distance == 2
    assert scored.tier == "coordinated"
    assert scored.severity == 0


def test_gap_rows_reads_live_hydradb_lineage() -> None:
    settings = settings_from_env({"XRAY_HYDRA_URI": "bolt://hydra.example:7687"})

    rows = gap_rows(settings, demo_bundle(), gateway=HydraGateway(GapRowsDriver()))

    assert rows is not None
    assert rows[0].phantom_key == "artifact:missing-approval"
    assert rows[0].properties["expected_kind"] == "approval"
    assert rows[0].predecessor_keys == ("artifact:directive",)
    assert rows[0].successor_keys == ("artifact:code-change",)


def test_live_ghost_findings_use_single_integer_id_mspaths_call() -> None:
    settings = settings_from_env({"XRAY_HYDRA_URI": "bolt://hydra.example:7687"})
    driver = GhostPathsDriver()

    result = live_ghost_findings(settings, demo_bundle(), gateway=HydraGateway(driver))

    assert result is not None
    assert result.error is None
    assert result.executed_query.round_trips == 1
    assert "sourceProperty: 'path_key'" in result.executed_query.text
    assert "sourceLabel: 'Person'" in result.executed_query.text
    assert "canonical_key" not in result.executed_query.text
    assert "pairwise: false" in result.executed_query.text
    assert driver.parameters == [{}]
    maya = next(
        finding for finding in result.findings if finding["person_key"] == "person:maya-chen"
    )
    assert maya["sampled_centrality"] > 0


def test_live_gap_chain_uses_integer_id_sppaths_call() -> None:
    settings = settings_from_env({"XRAY_HYDRA_URI": "bolt://hydra.example:7687"})
    driver = GapChainDriver()

    result = live_gap_chain(
        settings,
        demo_bundle(),
        source_artifact_key="artifact:code-change",
        target_artifact_key="artifact:directive",
        gateway=HydraGateway(driver),
    )

    assert result is not None
    assert result.error is None
    assert result.node_keys == (
        "artifact:code-change",
        "artifact:missing-approval",
        "artifact:directive",
    )
    assert "sourceNode: $source_id" in result.executed_query.text
    assert "targetNode: $target_id" in result.executed_query.text
    assert result.executed_query.params == {
        "source_id": 5711979473372363488,
        "target_id": 9197572505128004661,
    }
    assert driver.parameters == [result.executed_query.params]


def test_gap_chain_can_be_attached_to_matching_finding() -> None:
    from xray_analytics import GapFinding
    from xray_api.app import _with_gap_evidence

    finding = GapFinding(
        phantom_key="artifact:missing-approval",
        expected_kind="approval",
        reason="required_sequence_step_missing",
        inferred_epoch=1736003600,
        predecessor_keys=("artifact:directive",),
        successor_keys=("artifact:code-change",),
    )

    enriched = _with_gap_evidence(
        demo_bundle(),
        (finding,),
        chain={
            "node_keys": (
                "artifact:code-change",
                "artifact:missing-approval",
                "artifact:directive",
            ),
            "phantom_indices": (1,),
        },
    )

    assert enriched[0]["chain"] == {
        "node_keys": (
            "artifact:code-change",
            "artifact:missing-approval",
            "artifact:directive",
        ),
        "phantom_indices": (1,),
    }


def test_faultlines_endpoint_returns_no_path_coordination_debt() -> None:
    payload = client().get("/api/v1/snapshots/xray-demo-v1:fixture/faultlines").json()

    assert payload["analysis_status"] == "complete"
    assert payload["findings"][0]["source_module_key"] == "module:payments-api"
    assert payload["findings"][0]["tier"] == "no_path"
    assert {record["predicate"] for record in payload["findings"][0]["evidence"]} >= {
        "authorship_aggregate",
        "dependency",
    }


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
    assert payload["findings"][0]["evidence"][0]["predicate"] == "gap_phantom"
    assert "Absence does not establish deletion" in payload["status_explanation"]


def test_unknown_snapshot_returns_problem_detail() -> None:
    response = client().get("/api/v1/snapshots/missing/ghosts")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "snapshot_not_found"


def test_ghosts_endpoint_fixture_what_if_reports_pairs_lost_and_comparison() -> None:
    payload = (
        client()
        .get(
            "/api/v1/snapshots/xray-demo-v1:fixture/ghosts",
            params={"exclude": ["person:maya-chen"]},
        )
        .json()
    )

    assert payload["source"] == "fixture"
    what_if = payload["what_if"]
    assert what_if["excluded_person_keys"] == ["person:maya-chen"]
    assert what_if["pairs_lost"] > 0
    assert what_if["sampled_pairs_before"] > what_if["sampled_pairs_after"]
    assert all(f["person_key"] != "person:maya-chen" for f in payload["findings"])
    comparison = payload["comparison"]
    assert comparison["engine_ms"] is None
    assert comparison["client_equivalent_round_trips"] == 45
    assert comparison["client_method"] == "python_bounded_bfs_all_pairs"
