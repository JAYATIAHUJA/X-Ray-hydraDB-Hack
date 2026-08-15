from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from xray_analytics import bus_factor_impact, faultlines, gap_findings, ghost_scores
from xray_core.models import AnalysisStatus

from .dependencies import current_snapshot_id, demo_bundle
from .errors import not_found
from .schemas import GapPathRequest, HealthResponse, LensEnvelope, SnapshotResponse


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
        return HealthResponse(status="ok")

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
            explanation="Fixture Ghost analysis completed with bounded in-memory path scoring.",
        )

    @app.get("/api/v1/snapshots/{snapshot_id}/faultlines", response_model=LensEnvelope)
    def faultline_results(snapshot_id: str) -> LensEnvelope:
        _require_current_snapshot(snapshot_id)
        bundle = demo_bundle()
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=bundle.limitations,
            findings=tuple(asdict(finding) for finding in faultlines(bundle)),
            explanation="Fixture Faultline analysis completed over derived ownership and dependencies.",
        )

    @app.post("/api/v1/snapshots/{snapshot_id}/gap-paths", response_model=LensEnvelope)
    def gap_paths(snapshot_id: str, request: GapPathRequest) -> LensEnvelope:
        _require_current_snapshot(snapshot_id)
        bundle = demo_bundle()
        findings = tuple(
            asdict(finding)
            for finding in gap_findings(bundle)
            if request.target_artifact_key in finding.predecessor_keys
            and request.source_artifact_key in finding.successor_keys
        )
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=bundle.limitations,
            findings=findings,
            explanation=(
                "Fixture Gap analysis completed under explicit sequence contracts. "
                "Absence does not establish deletion."
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


app = create_app()


__all__ = ["app", "create_app"]
