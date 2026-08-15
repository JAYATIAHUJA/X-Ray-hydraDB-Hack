from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from xray_analytics import (
    FaultlineFinding,
    GapFinding,
    GhostScore,
    bus_factor_impact,
    faultlines,
    gap_findings,
    ghost_scores,
)
from xray_core.models import AnalysisStatus, EdgeRow, NodeRow

from .config import get_settings
from .dependencies import current_snapshot_id, demo_bundle
from .errors import not_found
from .hydra import (
    HydraGapRow,
    HydraGraphEdge,
    HydraGraphNode,
    HydraHealth,
    communication_distances,
    gap_rows,
    graph_rows,
    hydra_health,
    seed_bundle,
)
from .schemas import (
    GapPathRequest,
    GraphEdge,
    GraphNode,
    GraphResponse,
    HealthResponse,
    HydraHealthResponse,
    HydraSeedResponse,
    LensEnvelope,
    LoadReportResponse,
    SnapshotResponse,
)

PERSON_LAYOUT = {
    "person:maya-chen": (50, 49),
    "person:alex-rivera": (50, 16),
    "person:priya-shah": (32, 24),
    "person:omar-haddad": (65, 55),
    "person:lena-park": (38, 64),
    "person:theo-brooks": (48, 82),
    "person:nina-okafor": (18, 56),
    "person:sam-wu": (78, 30),
    "person:ines-costa": (82, 52),
    "person:jon-bell": (73, 72),
}


def create_app() -> FastAPI:
    app = FastAPI(title="X-Ray Evidence Platform API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["content-type"],
    )

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        hydra = hydra_health(get_settings())
        return HealthResponse(
            status="ok",
            hydra=_hydra_health_response(hydra),
        )

    @app.post("/api/v1/hydra/seed-fixture", response_model=HydraSeedResponse)
    def seed_fixture() -> HydraSeedResponse:
        result = seed_bundle(get_settings(), demo_bundle())
        report = result.report
        return HydraSeedResponse(
            status=result.status,
            detail=result.detail,
            hydra=_hydra_health_response(result.hydra),
            report=None
            if report is None
            else LoadReportResponse(
                snapshot_id=report.snapshot_id,
                node_count=report.node_count,
                edge_count=report.edge_count,
                attempted_batches=report.attempted_batches,
                completed_batches=report.completed_batches,
                resumed_batches=report.resumed_batches,
                failed_batches=report.failed_batches,
                graph_fingerprint=report.graph_fingerprint,
            ),
        )

    @app.get("/api/v1/snapshots/current", response_model=SnapshotResponse)
    def current_snapshot() -> SnapshotResponse:
        bundle = demo_bundle()
        return SnapshotResponse(
            snapshot_id=current_snapshot_id(),
            dataset_id=bundle.dataset_id,
            node_count=len(bundle.nodes),
            edge_count=len(bundle.edges),
            evidence_count=len(bundle.evidence),
            limitations=bundle.limitations,
        )

    @app.get("/api/v1/snapshots/{snapshot_id}/graph", response_model=GraphResponse)
    def graph(snapshot_id: str) -> GraphResponse:
        _require_current_snapshot(snapshot_id)
        bundle = demo_bundle()
        scores = {score.person_key: score for score in ghost_scores(bundle)}
        selected_key = max(scores.values(), key=lambda score: score.rank_gap).person_key
        hydra_rows = graph_rows(get_settings(), bundle.dataset_id)
        if hydra_rows is not None and hydra_rows.nodes:
            return GraphResponse(
                snapshot_id=snapshot_id,
                nodes=tuple(
                    _hydra_graph_node(row, scores.get(row.key), selected_key)
                    for row in hydra_rows.nodes
                ),
                edges=tuple(_hydra_graph_edge(edge) for edge in hydra_rows.edges),
            )

        people = tuple(
            sorted(
                (node for node in bundle.nodes if node.label == "Person"),
                key=lambda node: node.canonical_key,
            )
        )
        node_key_by_id = {node.id: node.canonical_key for node in people}

        return GraphResponse(
            snapshot_id=snapshot_id,
            nodes=tuple(
                _graph_node(node, scores.get(node.canonical_key), selected_key) for node in people
            ),
            edges=tuple(
                _graph_edge(edge, node_key_by_id)
                for edge in sorted(bundle.edges, key=lambda item: item.canonical_key)
                if edge.rel_type == "COMMUNICATES"
                and edge.source_id in node_key_by_id
                and edge.target_id in node_key_by_id
            ),
        )

    @app.get("/api/v1/snapshots/{snapshot_id}/ghosts", response_model=LensEnvelope)
    def ghosts(snapshot_id: str) -> LensEnvelope:
        _require_current_snapshot(snapshot_id)
        bundle = demo_bundle()
        scores = ghost_scores(bundle)
        findings = []
        for score in scores:
            impact = bus_factor_impact(bundle, score.person_key)
            findings.append({**asdict(score), "removal_impact": asdict(impact)})
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=bundle.limitations,
            findings=tuple(findings),
            explanation=(
                "HydraDB graph rows were available; Ghost scoring completed with bounded fallback path scoring."
                if graph_rows(get_settings(), bundle.dataset_id) is not None
                else "Fixture Ghost analysis completed with bounded in-memory path scoring."
            ),
        )

    @app.get("/api/v1/snapshots/{snapshot_id}/faultlines", response_model=LensEnvelope)
    def faultline_results(snapshot_id: str) -> LensEnvelope:
        _require_current_snapshot(snapshot_id)
        bundle = demo_bundle()
        findings = faultlines(bundle)
        distances = communication_distances(
            get_settings(),
            bundle.dataset_id,
            tuple((finding.source_owner_key, finding.target_owner_key) for finding in findings),
        )
        if distances is not None:
            live_findings = tuple(_with_live_distance(finding, distances) for finding in findings)
            findings = tuple(finding for finding in live_findings if finding.severity > 0)
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=bundle.limitations,
            findings=tuple(asdict(finding) for finding in findings),
            explanation=(
                "HydraDB Faultline analysis completed with live owner communication distance queries."
                if distances is not None
                else "Fixture Faultline analysis completed over derived ownership and dependencies."
            ),
        )

    @app.post("/api/v1/snapshots/{snapshot_id}/gap-paths", response_model=LensEnvelope)
    def gap_paths(snapshot_id: str, request: GapPathRequest) -> LensEnvelope:
        _require_current_snapshot(snapshot_id)
        bundle = demo_bundle()
        live_gaps = gap_rows(get_settings(), bundle.dataset_id)
        all_findings = (
            tuple(_gap_finding_from_hydra(row) for row in live_gaps)
            if live_gaps is not None
            else gap_findings(bundle)
        )
        findings = tuple(
            asdict(finding)
            for finding in all_findings
            if (
                request.target_artifact_key in finding.predecessor_keys
                and request.source_artifact_key in finding.successor_keys
            )
            or finding.reason == "dangling_thread_parent"
        )
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=bundle.limitations,
            findings=findings,
            explanation=(
                (
                    "HydraDB Gap analysis completed from live phantom lineage rows. "
                    if live_gaps is not None
                    else "Fixture Gap analysis completed under explicit sequence contracts. "
                )
                + "Absence does not establish deletion."
            ),
        )

    return app


def _require_current_snapshot(snapshot_id: str) -> None:
    if snapshot_id != current_snapshot_id():
        raise not_found(f"Unknown snapshot {snapshot_id!r}", code="snapshot_not_found")


def _lens_envelope(
    *,
    snapshot_id: str,
    limitations: tuple[str, ...],
    findings: tuple[dict[str, object], ...],
    explanation: str,
) -> LensEnvelope:
    return LensEnvelope(
        snapshot_id=snapshot_id,
        analysis_status=AnalysisStatus.COMPLETE,
        status_explanation=explanation,
        limitations=limitations,
        findings=findings,
    )


def _hydra_health_response(hydra: HydraHealth) -> HydraHealthResponse:
    return HydraHealthResponse(
        status=hydra.status,
        configured=hydra.configured,
        database=hydra.database,
        uri=hydra.uri,
        detail=hydra.detail,
    )


def _with_live_distance(
    finding: FaultlineFinding,
    distances: dict[tuple[str, str], int | None],
) -> FaultlineFinding:
    distance = distances.get((finding.source_owner_key, finding.target_owner_key))
    if distance is None:
        tier = "no_path"
        risk = 1.0
    elif distance >= 3:
        tier = "weak_coordination"
        risk = 0.5
    else:
        tier = "coordinated"
        risk = 0.0
    return FaultlineFinding(
        source_module_key=finding.source_module_key,
        target_module_key=finding.target_module_key,
        source_owner_key=finding.source_owner_key,
        target_owner_key=finding.target_owner_key,
        dependency_weight=finding.dependency_weight,
        source_owner_confidence=finding.source_owner_confidence,
        target_owner_confidence=finding.target_owner_confidence,
        communication_distance=distance,
        tier=tier,
        severity=finding.dependency_weight * risk,
    )


def _gap_finding_from_hydra(row: HydraGapRow) -> GapFinding:
    expected_kind = row.properties.get("expected_kind")
    reason = row.properties.get("reason")
    inferred_epoch = row.properties.get("inferred_epoch")
    return GapFinding(
        phantom_key=row.phantom_key,
        expected_kind=expected_kind if isinstance(expected_kind, str) else "unknown",
        reason=reason if isinstance(reason, str) else "unknown",
        inferred_epoch=inferred_epoch if type(inferred_epoch) is int else None,
        predecessor_keys=row.predecessor_keys,
        successor_keys=row.successor_keys,
    )


def _graph_node(node: NodeRow, score: GhostScore | None, selected_key: str) -> GraphNode:
    properties = node.properties
    team = str(properties.get("team_id", "team:unknown")).removeprefix("team:")
    role_rank = int(properties.get("role_rank", 1))
    centrality = getattr(score, "sampled_centrality", 0.0)
    degree = getattr(score, "communication_degree", 0)
    x, y = PERSON_LAYOUT.get(node.canonical_key, (50, 50))
    return GraphNode(
        key=node.canonical_key,
        name=str(properties.get("display_name", node.canonical_key)),
        title=_person_title(team, role_rank),
        team=team,
        x=x,
        y=y,
        official_size=max(20, 78 - (role_rank * 10)),
        actual_size=max(20, min(82, round(20 + (centrality * 250) + (degree * 3)))),
        selected=node.canonical_key == selected_key,
    )


def _hydra_graph_node(
    node: HydraGraphNode, score: GhostScore | None, selected_key: str
) -> GraphNode:
    team = str(node.properties.get("team_id", "team:unknown")).removeprefix("team:")
    role_rank = int(node.properties.get("role_rank", 1))
    centrality = getattr(score, "sampled_centrality", 0.0)
    degree = getattr(score, "communication_degree", 0)
    x, y = PERSON_LAYOUT.get(node.key, (50, 50))
    return GraphNode(
        key=node.key,
        name=str(node.properties.get("display_name", node.key)),
        title=_person_title(team, role_rank),
        team=team,
        x=x,
        y=y,
        official_size=max(20, 78 - (role_rank * 10)),
        actual_size=max(20, min(82, round(20 + (centrality * 250) + (degree * 3)))),
        selected=node.key == selected_key,
    )


def _graph_edge(edge: EdgeRow, node_key_by_id: dict[int, str]) -> GraphEdge:
    weight = edge.properties.get("weight", 0)
    return GraphEdge(
        source=node_key_by_id[edge.source_id],
        target=node_key_by_id[edge.target_id],
        strength=_edge_strength(float(weight)),
    )


def _hydra_graph_edge(edge: HydraGraphEdge) -> GraphEdge:
    return GraphEdge(
        source=edge.source,
        target=edge.target,
        strength=_edge_strength(edge.weight),
    )


def _edge_strength(weight: float) -> str:
    if weight >= 5:
        return "strong"
    if weight >= 3:
        return "medium"
    return "weak"


def _person_title(team: str, role_rank: int) -> str:
    team_name = team.replace("-", " ").capitalize()
    if role_rank >= 4:
        return f"{team_name} director"
    if role_rank == 3:
        return f"{team_name} lead"
    if role_rank == 2:
        return f"{team_name} partner"
    return f"{team_name} specialist"


app = create_app()


__all__ = ["app", "create_app"]
