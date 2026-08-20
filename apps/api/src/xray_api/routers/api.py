from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from xray_analytics import (
    FaultlineFinding,
    GapFinding,
    GhostScore,
    answer_ontology_question,
    apply_approved_repairs,
    communication_asymmetries,
    faultline_tier,
    faultlines,
    gap_findings,
    ghost_scores,
    identity_candidates,
    propose_repairs,
    shortest_communication_bridge,
    verify_repair,
    with_status,
)
from xray_analytics.questions import answer_from_hydra_rows
from xray_analytics.repairs import ApprovedRepair
from xray_analytics.verdicts import decide_question_verdict
from xray_core.models import (
    AnalysisStatus,
    CanonicalBundle,
    EdgeRow,
    EvidenceRecord,
    NodeRow,
)
from xray_core.paths import normalize_pair
from xray_hydra import HydraGateway, ontology_context_query

from ..config import XraySettings, get_settings
from ..dependencies import (
    get_gateway,
)
from ..errors import not_found
from ..hydra import (
    HydraGapRow,
    HydraGraphEdge,
    HydraGraphNode,
    communication_distances,
    gap_rows,
    graph_rows,
    hydra_health,
)
from ..lenses import (
    client_ghost_baseline_ms,
    fixture_ghost_findings,
    fixture_what_if,
    live_gap_chain,
    live_ghost_findings,
)
from ..schemas import (
    EngineComparison,
    GapPathRequest,
    GraphEdge,
    GraphNode,
    GraphResponse,
    IdentityCandidateResponse,
    IdentityDecisionRequest,
    LensEnvelope,
    QuestionRequest,
    QuestionResponse,
    RepairDecisionRequest,
    RepairProposalResponse,
    RepairVerifyResponse,
    WhatIfSummary,
)
from ..services.access import require_write_access
from ..services.reports import render_risk_report
from ..services.snapshots import SnapshotService
from .snapshots import snapshot_router
from .system import system_router

SettingsDep = Annotated[XraySettings, Depends(get_settings)]
GatewayDep = Annotated[HydraGateway | None, Depends(get_gateway)]


def create_app() -> FastAPI:
    app = FastAPI(title="X-Ray Evidence Platform API", version="0.1.0")
    snapshots = SnapshotService()
    identity_decisions: dict[tuple[str, str], str] = {}
    repair_ledger: dict[tuple[str, str], dict[str, object]] = {}
    # Extra origins for deployed frontends, comma-separated (the demo compose/Fly setup
    # proxies /api same-origin, so it needs none of this).
    extra_origins = [
        origin.strip()
        for origin in os.environ.get("XRAY_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", *extra_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["content-type", "X-Xray-Write-Token"],
    )
    app.include_router(system_router(snapshots))
    app.include_router(snapshot_router(snapshots))

    @app.get("/api/v1/snapshots/{snapshot_id}/risk-report", response_class=PlainTextResponse)
    def risk_report(snapshot_id: str) -> str:
        """Export the current evidence-backed findings as a portable Markdown report."""
        bundle = snapshots.require(snapshot_id)
        ghost_findings = _with_ghost_evidence(bundle, fixture_ghost_findings(bundle)[:1])
        faultline_findings = _with_faultline_evidence(bundle, faultlines(bundle)[:3])
        gap_findings_list = _with_gap_evidence(bundle, gap_findings(bundle)[:10])
        return render_risk_report(
            bundle,
            snapshot_id,
            ghosts=ghost_findings,
            faultlines=faultline_findings,
            gaps=gap_findings_list,
        )

    @app.get("/api/v1/snapshots/{snapshot_id}/graph", response_model=GraphResponse)
    def graph(
        snapshot_id: str,
        settings: SettingsDep,
        gateway: GatewayDep,
        window_days: Annotated[int, Query(ge=0, le=3650)] = 0,
    ) -> GraphResponse:
        bundle = _window_bundle(snapshots.require(snapshot_id), window_days)
        ranked = ghost_scores(bundle)
        scores = {score.person_key: score for score in ranked}
        # Pre-select the story: the largest formal-vs-structural gap among the ten most
        # structurally central people (a low-centrality outlier is not the Ghost).
        selected_score = max(ranked[:10], key=lambda score: score.rank_gap, default=None)
        selected_key = None if selected_score is None else selected_score.person_key
        hydra_rows = graph_rows(settings, bundle, gateway=gateway)
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
                (
                    node
                    for node in bundle.nodes
                    if node.label == "Person"
                    and node.properties.get("identity_status") != "unresolved"
                ),
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
    def ghosts(
        snapshot_id: str,
        settings: SettingsDep,
        gateway: GatewayDep,
        exclude: Annotated[list[str] | None, Query()] = None,
        window_days: Annotated[int, Query(ge=0, le=3650)] = 0,
    ) -> LensEnvelope:
        """Ghost lens. Pass ``?exclude=person:...`` (repeatable) for a what-if removal."""
        bundle = _window_bundle(snapshots.require(snapshot_id), window_days)
        excluded = _validated_person_keys(bundle, exclude or [])
        client_ms = client_ghost_baseline_ms(bundle)
        live_result = live_ghost_findings(
            settings, bundle, gateway=gateway, exclude_person_keys=excluded
        )
        # Empty Hydra (ping OK, no dataset graph) must not mask fixture Ghosts.
        if (
            live_result is not None
            and live_result.error is None
            and not hydra_health(settings, bundle.dataset_id).graph_loaded
        ):
            live_result = None
        if live_result is not None and live_result.error is None:
            comparison = EngineComparison(
                engine_ms=live_result.executed_query.engine_ms,
                client_ms=client_ms,
                client_method="python_bounded_bfs_all_pairs",
                sampled_people=live_result.sampled_people,
                engine_round_trips=live_result.executed_query.round_trips,
                client_equivalent_round_trips=_pairwise_round_trips(live_result.sampled_people),
            )
            return _lens_envelope(
                snapshot_id=snapshot_id,
                limitations=bundle.limitations,
                findings=_with_ghost_evidence(bundle, live_result.findings),
                explanation="HydraDB Ghost analysis completed with one bounded MSpaths sample call.",
                source="hydradb",
                executed_query=asdict(live_result.executed_query),
                what_if=None if live_result.what_if is None else asdict(live_result.what_if),
                comparison=comparison,
            )
        findings = fixture_ghost_findings(bundle, exclude_person_keys=excluded)
        people_count = sum(
            1
            for node in bundle.nodes
            if node.label == "Person" and node.properties.get("identity_status") != "unresolved"
        )
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
            source="fixture",
            degraded_reason=None if live_result is None else live_result.error,
            executed_query=None if live_result is None else asdict(live_result.executed_query),
            what_if=None if not excluded else asdict(fixture_what_if(bundle, excluded)),
            comparison=EngineComparison(
                engine_ms=None,
                client_ms=client_ms,
                client_method="python_bounded_bfs_all_pairs",
                sampled_people=people_count,
                engine_round_trips=0,
                client_equivalent_round_trips=_pairwise_round_trips(people_count),
            ),
        )

    @app.get("/api/v1/snapshots/{snapshot_id}/faultlines", response_model=LensEnvelope)
    def faultline_results(
        snapshot_id: str,
        settings: SettingsDep,
        gateway: GatewayDep,
        window_days: Annotated[int, Query(ge=0, le=3650)] = 0,
    ) -> LensEnvelope:
        bundle = _window_bundle(snapshots.require(snapshot_id), window_days)
        findings = faultlines(bundle)
        distance_result = communication_distances(
            settings,
            bundle,
            tuple((finding.source_owner_key, finding.target_owner_key) for finding in findings),
            gateway=gateway,
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

    @app.get("/api/v1/snapshots/{snapshot_id}/gaps", response_model=LensEnvelope)
    def gaps(
        snapshot_id: str,
        settings: SettingsDep,
        gateway: GatewayDep,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> LensEnvelope:
        """All Phantom findings for the snapshot (no chain); use gap-paths for one chain."""
        bundle = snapshots.require(snapshot_id)
        live_gaps = gap_rows(settings, bundle, gateway=gateway)
        bundle_has_phantoms = any(node.label == "Phantom" for node in bundle.nodes)
        if live_gaps is not None and not live_gaps and bundle_has_phantoms:
            live_gaps = None
        all_findings = (
            tuple(_gap_finding_from_hydra(row) for row in live_gaps)
            if live_gaps is not None
            else gap_findings(bundle)
        )
        # Contract-declared missing steps first (they carry the strongest structural claim),
        # then in-window dangling parents (the corpus should contain them and does not),
        # then export-boundary ones (parent most likely predates the export); stable within
        # each group.
        ordered = sorted(
            all_findings,
            key=lambda f: (
                f.reason == "dangling_thread_parent",
                f.window_position == "export_boundary",
                -(f.days_after_corpus_start or 0),
                f.phantom_key,
            ),
        )
        in_window = sum(1 for f in all_findings if f.window_position == "in_window")
        boundary = sum(1 for f in all_findings if f.window_position == "export_boundary")
        position_note = (
            f" — {in_window} inside the export window, {boundary} at its boundary"
            if in_window or boundary
            else ""
        )
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=bundle.limitations,
            findings=_with_gap_evidence(bundle, tuple(ordered[:limit])),
            explanation=(
                f"{len(all_findings)} structurally missing records{position_note}"
                + (f" (showing {limit})" if len(all_findings) > limit else "")
                + ". Absence does not establish deletion."
            ),
            source="hydradb" if live_gaps is not None else "fixture",
            total_findings=len(all_findings),
        )

    @app.post("/api/v1/snapshots/{snapshot_id}/gap-paths", response_model=LensEnvelope)
    def gap_paths(
        snapshot_id: str,
        request: GapPathRequest,
        settings: SettingsDep,
        gateway: GatewayDep,
    ) -> LensEnvelope:
        bundle = snapshots.require(snapshot_id)
        live_chain = live_gap_chain(
            settings,
            bundle,
            source_artifact_key=request.source_artifact_key,
            target_artifact_key=request.target_artifact_key,
            gateway=gateway,
        )
        live_gaps = gap_rows(settings, bundle, gateway=gateway)
        bundle_has_phantoms = any(node.label == "Phantom" for node in bundle.nodes)
        if live_gaps is not None and not live_gaps and bundle_has_phantoms:
            # The engine answered but holds no phantom rows for this dataset (seed not
            # applied yet). Serve the bundle's findings and say so rather than an empty lens.
            live_gaps = None
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

    @app.post(
        "/api/v1/snapshots/{snapshot_id}/questions",
        response_model=QuestionResponse,
    )
    def answer_question(
        snapshot_id: str,
        request: QuestionRequest,
        settings: SettingsDep,
        gateway: GatewayDep,
    ) -> QuestionResponse:
        bundle = snapshots.require(snapshot_id)
        provisional = answer_ontology_question(bundle, request.question)
        answer = provisional
        source: Literal["fixture", "hydradb"] = "fixture"
        degraded_reason = None
        executed_query: dict[str, object] | None = None
        engine_ms = None
        round_trips = 0
        # Prefer snapshot answers when Hydra is reachable but this dataset is not loaded.
        hydra_graph_ready = (
            gateway is not None and hydra_health(settings, bundle.dataset_id).graph_loaded
        )
        if (
            hydra_graph_ready
            and provisional.subject_key is not None
            and provisional.intent in {"owner", "dependency_impact", "approval"}
        ):
            query = ontology_context_query(
                provisional.intent, bundle.dataset_id, provisional.subject_key
            )
            started = time.perf_counter()
            try:
                rows = gateway.run(query)
                engine_ms = (time.perf_counter() - started) * 1000
                round_trips = 1
                hydra_answer = answer_from_hydra_rows(provisional, rows, bundle)
                if hydra_answer is not None:
                    answer = hydra_answer
                    source = "hydradb"
                executed_query = {
                    "text": query.statement,
                    "params": dict(query.parameters),
                    "max_len": query.max_len,
                    "round_trips": 1,
                    "engine_ms": engine_ms,
                }
            except Exception as exc:
                engine_ms = (time.perf_counter() - started) * 1000
                round_trips = 1
                degraded_reason = str(exc)
                executed_query = {
                    "text": query.statement,
                    "params": dict(query.parameters),
                    "max_len": query.max_len,
                    "round_trips": 1,
                    "engine_ms": engine_ms,
                }
        evidence = {item.evidence_id: item for item in bundle.evidence}
        return QuestionResponse(
            snapshot_id=snapshot_id,
            evidence=_evidence_summaries(evidence, answer.evidence_ids, limit=20),
            source=source,
            degraded_reason=degraded_reason,
            executed_query=executed_query,
            engine_ms=engine_ms,
            round_trips=round_trips,
            verdict=decide_question_verdict(answer),
            **asdict(answer),
        )

    @app.get(
        "/api/v1/snapshots/{snapshot_id}/identity-candidates",
        response_model=tuple[IdentityCandidateResponse, ...],
    )
    def get_identity_candidates(snapshot_id: str) -> tuple[IdentityCandidateResponse, ...]:
        bundle = snapshots.require(snapshot_id)
        decisions = {
            candidate_id: decision
            for (decision_snapshot, candidate_id), decision in identity_decisions.items()
            if decision_snapshot == snapshot_id
        }
        return tuple(
            IdentityCandidateResponse.model_validate(asdict(candidate))
            for candidate in identity_candidates(bundle, decisions)
        )

    @app.post(
        "/api/v1/snapshots/{snapshot_id}/identity-candidates/{candidate_id}/decision",
        response_model=IdentityCandidateResponse,
    )
    def decide_identity_candidate(
        snapshot_id: str,
        candidate_id: str,
        request: IdentityDecisionRequest,
        settings: SettingsDep,
        write_token: Annotated[str | None, Header(alias="X-Xray-Write-Token")] = None,
    ) -> IdentityCandidateResponse:
        require_write_access(settings, write_token)
        bundle = snapshots.require(snapshot_id)
        candidates = {item.candidate_id: item for item in identity_candidates(bundle)}
        if candidate_id not in candidates:
            raise not_found(
                f"Identity candidate {candidate_id!r} does not exist in this snapshot.",
                code="identity_candidate_not_found",
            )
        identity_decisions[(snapshot_id, candidate_id)] = request.decision
        updated = next(
            item
            for item in identity_candidates(bundle, {candidate_id: request.decision})
            if item.candidate_id == candidate_id
        )
        return IdentityCandidateResponse.model_validate(asdict(updated))

    @app.get(
        "/api/v1/snapshots/{snapshot_id}/repairs",
        response_model=tuple[RepairProposalResponse, ...],
    )
    def get_repairs(snapshot_id: str) -> tuple[RepairProposalResponse, ...]:
        bundle = snapshots.require(snapshot_id)
        statuses = {
            repair_id: str(entry["status"])
            for (sid, repair_id), entry in repair_ledger.items()
            if sid == snapshot_id
        }
        closed_map = {
            repair_id: bool(entry.get("closed", False))
            for (sid, repair_id), entry in repair_ledger.items()
            if sid == snapshot_id
        }
        responses: dict[str, RepairProposalResponse] = {
            item.repair_id: RepairProposalResponse.model_validate(asdict(item))
            for item in with_status(propose_repairs(bundle), statuses=statuses, closed=closed_map)
        }
        for (sid, repair_id), entry in repair_ledger.items():
            if sid != snapshot_id or repair_id in responses:
                continue
            stored = entry.get("proposal")
            if isinstance(stored, dict):
                responses[repair_id] = RepairProposalResponse.model_validate(
                    {
                        **stored,
                        "status": entry["status"],
                        "closed": bool(entry.get("closed", False)),
                    }
                )
        return tuple(sorted(responses.values(), key=lambda item: item.repair_id))

    @app.post(
        "/api/v1/snapshots/{snapshot_id}/repairs/{repair_id}/decision",
        response_model=RepairProposalResponse,
    )
    def decide_repair(
        snapshot_id: str,
        repair_id: str,
        request: RepairDecisionRequest,
        settings: SettingsDep,
        write_token: Annotated[str | None, Header(alias="X-Xray-Write-Token")] = None,
    ) -> RepairProposalResponse:
        require_write_access(settings, write_token)
        bundle = snapshots.require(snapshot_id)
        proposals = {item.repair_id: item for item in propose_repairs(bundle)}
        ledger_key = (snapshot_id, repair_id)
        proposal = proposals.get(repair_id)
        if proposal is None:
            stored = repair_ledger.get(ledger_key, {}).get("proposal")
            if not isinstance(stored, dict):
                raise not_found(
                    f"Repair {repair_id!r} does not exist in this snapshot.",
                    code="repair_not_found",
                )
            proposal_payload = stored
        else:
            proposal_payload = asdict(proposal)
        if request.decision == "rejected":
            repair_ledger[ledger_key] = {
                "status": "rejected",
                "closed": False,
                "proposal": proposal_payload,
            }
            return RepairProposalResponse.model_validate(
                {**proposal_payload, "status": "rejected", "closed": False}
            )

        approved = ApprovedRepair(
            repair_id=repair_id,
            repair_kind=proposal_payload["repair_kind"],  # type: ignore[arg-type]
            finding_kind=proposal_payload["finding_kind"],  # type: ignore[arg-type]
            finding_key=str(proposal_payload["finding_key"]),
            payload=_repair_payload(str(proposal_payload["finding_key"]), str(proposal_payload["repair_kind"])),
        )
        snapshots.replace_bundle(apply_approved_repairs(bundle, (approved,)))
        repair_ledger[ledger_key] = {
            "status": "approved",
            "closed": False,
            "proposal": proposal_payload,
            "approved": approved,
        }
        return RepairProposalResponse.model_validate(
            {**proposal_payload, "status": "approved", "closed": False}
        )

    @app.post(
        "/api/v1/snapshots/{snapshot_id}/repairs/{repair_id}/verify",
        response_model=RepairVerifyResponse,
    )
    def verify_repair_endpoint(snapshot_id: str, repair_id: str) -> RepairVerifyResponse:
        bundle = snapshots.require(snapshot_id)
        ledger_key = (snapshot_id, repair_id)
        entry = repair_ledger.get(ledger_key)
        proposal = next((item for item in propose_repairs(bundle) if item.repair_id == repair_id), None)
        if proposal is None and entry and isinstance(entry.get("proposal"), dict):
            from xray_analytics.repairs import RepairProposal

            stored = entry["proposal"]
            assert isinstance(stored, dict)
            proposal = RepairProposal(
                repair_id=str(stored["repair_id"]),
                finding_kind=stored["finding_kind"],  # type: ignore[arg-type]
                finding_key=str(stored["finding_key"]),
                title=str(stored["title"]),
                repair_kind=stored["repair_kind"],  # type: ignore[arg-type]
                summary=str(stored["summary"]),
                verdict=stored["verdict"],  # type: ignore[arg-type]
                evidence_ids=tuple(stored.get("evidence_ids") or ()),
                limitations=tuple(stored.get("limitations") or ()),
                status=str(entry.get("status", "approved")),  # type: ignore[arg-type]
            )
        if proposal is None:
            raise not_found(
                f"Repair {repair_id!r} does not exist in this snapshot.",
                code="repair_not_found",
            )
        closed, reason = verify_repair(bundle, proposal)
        status = "closed" if closed else str(entry.get("status", proposal.status) if entry else proposal.status)
        if entry is not None:
            entry["closed"] = closed
            entry["status"] = status
        return RepairVerifyResponse(
            repair_id=repair_id,
            closed=closed,
            reason=reason,
            status=status,  # type: ignore[arg-type]
        )

    @app.get("/api/v1/snapshots/{snapshot_id}/asymmetries", response_model=LensEnvelope)
    def asymmetries(
        snapshot_id: str,
        min_replies: Annotated[int, Query(ge=1, le=1000)] = 3,
        min_ratio: Annotated[float, Query(gt=1, le=100)] = 3.0,
    ) -> LensEnvelope:
        bundle = snapshots.require(snapshot_id)
        findings = tuple(
            asdict(finding)
            for finding in communication_asymmetries(
                bundle, min_replies=min_replies, min_ratio=min_ratio
            )
        )
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=tuple(
                sorted(
                    {
                        *bundle.limitations,
                        "Reply asymmetry is a team-level coordination prompt, not an employee performance score.",
                    }
                )
            ),
            findings=findings,
            explanation=(
                "Directed reply flow is preserved. Findings mark strong send/receive imbalance "
                "and require team context before interpretation."
            ),
        )

    return app


def _window_bundle(bundle: CanonicalBundle, window_days: int) -> CanonicalBundle:
    if window_days <= 0:
        return bundle
    observed_epochs = tuple(
        int(edge.properties["last_epoch"])
        for edge in bundle.edges
        if edge.rel_type == "COMMUNICATES" and type(edge.properties.get("last_epoch")) is int
    )
    if not observed_epochs:
        return bundle.model_copy(
            update={
                "limitations": tuple(
                    sorted(
                        {
                            *bundle.limitations,
                            f"The {window_days}-day communication window was not applied because no communication timestamps are available.",
                        }
                    )
                )
            }
        )
    reference_epoch = max(observed_epochs)
    cutoff = reference_epoch - (window_days * 86400)
    edges = tuple(
        edge
        for edge in bundle.edges
        if edge.rel_type != "COMMUNICATES"
        or (
            type(edge.properties.get("last_epoch")) is int
            and int(edge.properties["last_epoch"]) >= cutoff
        )
    )
    return bundle.model_copy(
        update={
            "edges": edges,
            "limitations": tuple(
                sorted(
                    {
                        *bundle.limitations,
                        f"Communication edges are filtered to the last {window_days} days ending at the latest observed communication ({reference_epoch}).",
                    }
                )
            ),
        }
    )


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
    what_if: dict[str, object] | None = None,
    comparison: EngineComparison | None = None,
    total_findings: int | None = None,
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
        what_if=None if what_if is None else WhatIfSummary.model_validate(what_if),
        comparison=comparison,
        total_findings=total_findings,
    )


def _validated_person_keys(bundle: CanonicalBundle, keys: list[str]) -> tuple[str, ...]:
    """Keep only keys that name people in the bundle; unknown keys are a 404, not a silent no-op."""
    people = {
        node.canonical_key
        for node in bundle.nodes
        if node.label == "Person" and node.properties.get("identity_status") != "unresolved"
    }
    unknown = sorted(key for key in keys if key not in people)
    if unknown:
        raise not_found(f"Unknown person keys: {', '.join(unknown)}", code="person_not_found")
    return tuple(sorted(set(keys)))


def _pairwise_round_trips(people: int) -> int:
    """Client-side equivalent of one pairwise MSpaths call: one shortest-path query per pair."""
    return people * (people - 1) // 2


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
            {
                **asdict(finding),
                "bridge": shortest_communication_bridge(
                    bundle,
                    finding.source_owner_key,
                    finding.target_owner_key,
                ),
                "evidence": _evidence_summaries(evidence, evidence_ids),
            }
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


def _repair_payload(finding_key: str, repair_kind: str) -> dict[str, str]:
    """Map a repair finding key into overlay payload fields."""
    if repair_kind == "record_missing_approval":
        return {"phantom_key": finding_key}
    parts = finding_key.split("|")
    if len(parts) != 4:
        return {}
    source_module, target_module, source_owner, target_owner = parts
    if repair_kind == "establish_owner_bridge":
        return {
            "source_owner_key": source_owner,
            "target_owner_key": target_owner,
            "source_module_key": source_module,
            "target_module_key": target_module,
        }
    return {
        "module_key": target_module,
        "source_owner_key": source_owner,
        "target_owner_key": target_owner,
    }


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


def _with_live_distance(
    finding: FaultlineFinding,
    distances: dict[tuple[str, str], int | None],
) -> FaultlineFinding:
    distance = distances.get(normalize_pair(finding.source_owner_key, finding.target_owner_key))
    tier, risk = faultline_tier(distance)
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
        window_position=(
            str(row.properties["window_position"])
            if isinstance(row.properties.get("window_position"), str)
            else "unknown"
        ),
        days_after_corpus_start=(
            int(row.properties["days_after_corpus_start"])
            if type(row.properties.get("days_after_corpus_start")) is int
            else None
        ),
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
