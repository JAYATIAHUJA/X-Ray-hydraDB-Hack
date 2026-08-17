from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from xray_analytics import (
    FaultlineFinding,
    GapFinding,
    GhostScore,
    faultlines,
    gap_findings,
    ghost_scores,
)
from xray_core.models import AnalysisStatus, CanonicalBundle, EdgeRow, EvidenceRecord, NodeRow

from .config import get_settings
from .dependencies import active_bundle, current_snapshot_id
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
from .lenses import fixture_ghost_findings, live_gap_chain, live_ghost_findings
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
        hydra = hydra_health(get_settings(), active_bundle().dataset_id)
        return HealthResponse(
            status="ok",
            hydra=_hydra_health_response(hydra),
        )

    @app.post("/api/v1/hydra/seed-fixture", response_model=HydraSeedResponse)
    def seed_fixture() -> HydraSeedResponse:
        result = seed_bundle(get_settings(), active_bundle())
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
        bundle = active_bundle()
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
        bundle = active_bundle()
        scores = {score.person_key: score for score in ghost_scores(bundle)}
        selected_score = max(scores.values(), key=lambda score: score.rank_gap, default=None)
        selected_key = None if selected_score is None else selected_score.person_key
        hydra_rows = graph_rows(get_settings(), bundle)
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
        bundle = active_bundle()
        live_result = live_ghost_findings(get_settings(), bundle)
        if live_result is not None and live_result.error is None:
            return _lens_envelope(
                snapshot_id=snapshot_id,
                limitations=bundle.limitations,
                findings=_with_ghost_evidence(bundle, live_result.findings),
                explanation="HydraDB Ghost analysis completed with one bounded MSpaths sample call.",
                source="hydradb",
                executed_query=asdict(live_result.executed_query),
            )
        findings = fixture_ghost_findings(bundle)
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=bundle.limitations,
            findings=_with_ghost_evidence(bundle, findings),
            explanation=(
                "HydraDB Ghost query degraded; fixture Ghost analysis completed with bounded in-memory path scoring."
                if live_result is not None
                else "Fixture Ghost analysis completed with bounded in-memory path scoring."
            ),
            status=AnalysisStatus.PARTIAL if live_result is not None else AnalysisStatus.COMPLETE,
            source="fixture" if live_result is None else "hydradb",
            degraded_reason=None if live_result is None else live_result.error,
            executed_query=None if live_result is None else asdict(live_result.executed_query),
        )

    @app.get("/api/v1/snapshots/{snapshot_id}/faultlines", response_model=LensEnvelope)
    def faultline_results(snapshot_id: str) -> LensEnvelope:
        _require_current_snapshot(snapshot_id)
        bundle = active_bundle()
        findings = faultlines(bundle)
        distance_result = communication_distances(
            get_settings(),
            bundle,
            tuple((finding.source_owner_key, finding.target_owner_key) for finding in findings),
        )
        if distance_result is not None and distance_result.error is None:
            live_findings = tuple(
                _with_live_distance(finding, distance_result.distances) for finding in findings
            )
            findings = tuple(finding for finding in live_findings if finding.severity > 0)
            source = "hydradb"
            status = AnalysisStatus.COMPLETE
            degraded_reason = None
        elif distance_result is not None:
            source = "hydradb"
            status = AnalysisStatus.PARTIAL
            degraded_reason = distance_result.error
        else:
            source = "fixture"
            status = AnalysisStatus.COMPLETE
            degraded_reason = None
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=bundle.limitations,
            findings=_with_faultline_evidence(bundle, findings),
            explanation=(
                "HydraDB Faultline analysis completed with live owner communication distance queries."
                if source == "hydradb" and degraded_reason is None
                else "Fixture Faultline analysis completed over derived ownership and dependencies."
            ),
            status=status,
            source=source,
            degraded_reason=degraded_reason,
            executed_query=None
            if distance_result is None
            else {
                "text": distance_result.query.statement,
                "params": distance_result.query.parameters,
                "max_len": distance_result.query.max_len,
                "round_trips": 1,
                "engine_ms": distance_result.duration_ms,
            },
        )

    @app.post("/api/v1/snapshots/{snapshot_id}/gap-paths", response_model=LensEnvelope)
    def gap_paths(snapshot_id: str, request: GapPathRequest) -> LensEnvelope:
        _require_current_snapshot(snapshot_id)
        bundle = active_bundle()
        live_chain = live_gap_chain(
            get_settings(),
            bundle,
            source_artifact_key=request.source_artifact_key,
            target_artifact_key=request.target_artifact_key,
        )
        live_gaps = gap_rows(get_settings(), bundle)
        all_findings = (
            tuple(_gap_finding_from_hydra(row) for row in live_gaps)
            if live_gaps is not None
            else gap_findings(bundle)
        )
        findings = tuple(
            finding
            for finding in all_findings
            if (
                request.target_artifact_key in finding.predecessor_keys
                and request.source_artifact_key in finding.successor_keys
            )
        )
        chain: dict[str, object] | None = None
        if live_chain is not None and live_chain.error is None and live_chain.node_keys:
            phantom_keys = {node.canonical_key for node in bundle.nodes if node.label == "Phantom"}
            chain = {
                "node_keys": live_chain.node_keys,
                "phantom_indices": tuple(
                    index
                    for index, node_key in enumerate(live_chain.node_keys)
                    if node_key in phantom_keys
                ),
            }
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=bundle.limitations,
            findings=_with_gap_evidence(bundle, findings, chain=chain),
            explanation=(
                (
                    "HydraDB Gap analysis completed from live SPpaths and phantom lineage rows. "
                    if live_chain is not None and live_chain.error is None and live_gaps is not None
                    else "HydraDB Gap SPpaths query degraded; fixture gap filtering completed. "
                    if live_chain is not None and live_chain.error is not None
                    else "Fixture Gap analysis completed under explicit sequence contracts. "
                )
                + "Absence does not establish deletion."
            ),
            status=(
                AnalysisStatus.PARTIAL
                if live_chain is not None and live_chain.error is not None
                else AnalysisStatus.COMPLETE
            ),
            source="hydradb" if live_chain is not None or live_gaps is not None else "fixture",
            degraded_reason=None if live_chain is None else live_chain.error,
            executed_query=None if live_chain is None else asdict(live_chain.executed_query),
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
    status: AnalysisStatus = AnalysisStatus.COMPLETE,
    source: str = "fixture",
    degraded_reason: str | None = None,
    executed_query: dict[str, object] | None = None,
) -> LensEnvelope:
    return LensEnvelope(
        snapshot_id=snapshot_id,
        analysis_status=status,
        status_explanation=explanation,
        limitations=limitations,
        findings=findings,
        source=source,
        degraded_reason=degraded_reason,
        executed_query=executed_query,
    )


def _with_ghost_evidence(
    bundle: CanonicalBundle, findings: tuple[dict[str, object], ...]
) -> tuple[dict[str, object], ...]:
    nodes = _nodes_by_key(bundle)
    evidence = _evidence_by_id(bundle)
    enriched: list[dict[str, object]] = []
    for finding in findings:
        person_key = finding.get("person_key")
        node = nodes.get(person_key) if isinstance(person_key, str) else None
        evidence_records = _evidence_summaries(evidence, () if node is None else node.evidence_ids)
        enriched.append({**finding, "evidence": evidence_records})
    return tuple(enriched)


def _with_faultline_evidence(
    bundle: CanonicalBundle, findings: tuple[FaultlineFinding, ...]
) -> tuple[dict[str, object], ...]:
    nodes = _nodes_by_key(bundle)
    edges = tuple(bundle.edges)
    evidence = _evidence_by_id(bundle)
    enriched: list[dict[str, object]] = []
    for finding in findings:
        dependency_evidence = _matching_edge_evidence_ids(
            edges,
            nodes,
            source_key=finding.source_module_key,
            target_key=finding.target_module_key,
            rel_type="DEPENDS_ON",
        )
        source_owner_evidence = _matching_edge_evidence_ids(
            edges,
            nodes,
            source_key=finding.source_owner_key,
            target_key=finding.source_module_key,
            rel_type="OWNS",
        )
        target_owner_evidence = _matching_edge_evidence_ids(
            edges,
            nodes,
            source_key=finding.target_owner_key,
            target_key=finding.target_module_key,
            rel_type="OWNS",
        )
        evidence_ids = tuple(
            dict.fromkeys((*dependency_evidence, *source_owner_evidence, *target_owner_evidence))
        )
        enriched.append(
            {**asdict(finding), "evidence": _evidence_summaries(evidence, evidence_ids)}
        )
    return tuple(enriched)


def _with_gap_evidence(
    bundle: CanonicalBundle,
    findings: tuple[GapFinding, ...],
    *,
    chain: dict[str, object] | None = None,
) -> tuple[dict[str, object], ...]:
    nodes = _nodes_by_key(bundle)
    evidence = _evidence_by_id(bundle)
    enriched: list[dict[str, object]] = []
    for finding in findings:
        phantom = nodes.get(finding.phantom_key)
        evidence_records = _evidence_summaries(
            evidence, () if phantom is None else phantom.evidence_ids
        )
        enriched_finding = {**asdict(finding), "evidence": evidence_records}
        chain_node_keys = chain.get("node_keys", ()) if chain is not None else ()
        if (
            chain is not None
            and isinstance(chain_node_keys, tuple)
            and finding.phantom_key in chain_node_keys
        ):
            enriched_finding["chain"] = chain
        enriched.append(enriched_finding)
    return tuple(enriched)


def _nodes_by_key(bundle: CanonicalBundle) -> dict[str, NodeRow]:
    return {node.canonical_key: node for node in bundle.nodes}


def _evidence_by_id(bundle: CanonicalBundle) -> dict[str, EvidenceRecord]:
    return {record.evidence_id: record for record in bundle.evidence}


def _matching_edge_evidence_ids(
    edges: tuple[EdgeRow, ...],
    nodes: dict[str, NodeRow],
    *,
    source_key: str,
    target_key: str,
    rel_type: str,
) -> tuple[str, ...]:
    source = nodes.get(source_key)
    target = nodes.get(target_key)
    if source is None or target is None:
        return ()
    return tuple(
        evidence_id
        for edge in edges
        if edge.rel_type == rel_type and edge.source_id == source.id and edge.target_id == target.id
        for evidence_id in edge.evidence_ids
    )


def _evidence_summaries(
    evidence: dict[str, EvidenceRecord], evidence_ids: tuple[str, ...], *, limit: int = 4
) -> tuple[dict[str, object], ...]:
    records = tuple(
        evidence[evidence_id] for evidence_id in evidence_ids if evidence_id in evidence
    )
    return tuple(
        {
            "evidence_id": record.evidence_id,
            "source_type": record.source_type,
            "source_uri": record.source_uri,
            "source_record_id": record.source_record_id,
            "predicate": record.predicate,
            "subject_key": record.subject_key,
            "object_key": record.object_key,
            "evidence_class": record.evidence_class.value,
            "confidence": record.confidence,
            "content_sha256": record.content_sha256,
            "redacted_excerpt": record.redacted_excerpt,
        }
        for record in records[:limit]
    )


def _hydra_health_response(hydra: HydraHealth) -> HydraHealthResponse:
    return HydraHealthResponse(
        status=hydra.status,
        configured=hydra.configured,
        database=hydra.database,
        uri=hydra.uri,
        detail=hydra.detail,
        graph_loaded=hydra.graph_loaded,
        node_count=hydra.node_count,
        edge_count=hydra.edge_count,
    )


def _with_live_distance(
    finding: FaultlineFinding,
    distances: dict[tuple[str, str], int | None],
) -> FaultlineFinding:
    distance = distances.get(_normalize_pair(finding.source_owner_key, finding.target_owner_key))
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


MIN_NODE_SIZE = 20
MAX_NODE_SIZE = 82


def _graph_node(node: NodeRow, score: GhostScore | None, selected_key: str | None) -> GraphNode:
    return _build_graph_node(node.canonical_key, node.properties, score, selected_key)


def _hydra_graph_node(
    node: HydraGraphNode, score: GhostScore | None, selected_key: str | None
) -> GraphNode:
    return _build_graph_node(node.key, node.properties, score, selected_key)


def _build_graph_node(
    key: str,
    properties: Mapping[str, object],
    score: GhostScore | None,
    selected_key: str | None,
) -> GraphNode:
    team = str(properties.get("team_id", "team:unknown")).removeprefix("team:")
    role_rank = _role_rank_value(properties.get("role_rank"))
    centrality = getattr(score, "sampled_centrality", 0.0)
    degree = getattr(score, "communication_degree", 0)
    return GraphNode(
        key=key,
        name=str(properties.get("display_name", key)),
        title=_person_title(team, role_rank),
        team=team,
        # Official size grows with formal seniority (spec §3.1: 1=IC … 6=VP+).
        official_size=max(MIN_NODE_SIZE, min(MAX_NODE_SIZE, 22 + (role_rank * 10))),
        actual_size=max(
            MIN_NODE_SIZE,
            min(MAX_NODE_SIZE, round(MIN_NODE_SIZE + (centrality * 250) + (degree * 3))),
        ),
        selected=key == selected_key,
    )


def _role_rank_value(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0


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


def _normalize_pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


ROLE_TITLES = {
    0: "member",
    1: "engineer",
    2: "senior engineer",
    3: "lead",
    4: "manager",
    5: "director",
}


def _person_title(team: str, role_rank: int) -> str:
    """Render a display title from the spec §3.1 role_rank scale (higher = more senior)."""
    team_name = team.replace("-", " ").capitalize()
    if role_rank >= 6:
        return f"VP, {team_name}"
    return f"{team_name} {ROLE_TITLES.get(role_rank, 'member')}"


app = create_app()


__all__ = ["app", "create_app"]
