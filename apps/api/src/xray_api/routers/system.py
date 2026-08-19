from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from xray_hydra import HydraGateway

from ..config import XraySettings, get_settings
from ..dependencies import get_gateway
from ..hydra import HydraHealth, hydra_health, seed_bundle
from ..schemas import (
    HealthResponse,
    HydraHealthResponse,
    HydraSeedResponse,
    LoadReportResponse,
)
from ..services.access import require_write_access
from ..services.snapshots import SnapshotService

SettingsDep = Annotated[XraySettings, Depends(get_settings)]
GatewayDep = Annotated[HydraGateway | None, Depends(get_gateway)]
WriteToken = Annotated[str | None, Header(alias="X-Xray-Write-Token")]


def system_router(snapshots: SnapshotService) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["system"])

    @router.get("/health", response_model=HealthResponse)
    def health(settings: SettingsDep) -> HealthResponse:
        hydra = hydra_health(settings, snapshots.current().bundle.dataset_id)
        return HealthResponse(
            status="ok",
            hydra=_health_response(hydra),
            read_only=settings.read_only,
            imports_enabled=settings.imports_enabled and not settings.read_only,
        )

    @router.post("/hydra/seed-fixture", response_model=HydraSeedResponse)
    def seed_fixture(
        settings: SettingsDep,
        gateway: GatewayDep,
        write_token: WriteToken = None,
    ) -> HydraSeedResponse:
        require_write_access(settings, write_token)
        result = seed_bundle(settings, snapshots.current().bundle, gateway=gateway)
        report = result.report
        return HydraSeedResponse(
            status=result.status,
            detail=result.detail,
            hydra=_health_response(result.hydra),
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

    return router


def _health_response(hydra: HydraHealth) -> HydraHealthResponse:
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


__all__ = ["system_router"]
