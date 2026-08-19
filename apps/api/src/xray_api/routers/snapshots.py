from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header

from ..config import XraySettings, get_settings
from ..schemas import ActivateSnapshotRequest, AvailableSnapshot, ImportRequest, SnapshotResponse
from ..services.access import require_write_access
from ..services.snapshots import SnapshotService

SettingsDep = Annotated[XraySettings, Depends(get_settings)]
WriteToken = Annotated[str | None, Header(alias="X-Xray-Write-Token")]


def snapshot_router(snapshots: SnapshotService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/snapshots", tags=["snapshots"])

    @router.get("/current", response_model=SnapshotResponse)
    def current_snapshot() -> SnapshotResponse:
        return snapshots.response()

    @router.get("/available", response_model=tuple[AvailableSnapshot, ...])
    def available_snapshots() -> tuple[AvailableSnapshot, ...]:
        return snapshots.available()

    @router.post("/activate", response_model=SnapshotResponse)
    def activate_snapshot(
        request: ActivateSnapshotRequest,
        settings: SettingsDep,
        write_token: WriteToken = None,
    ) -> SnapshotResponse:
        require_write_access(settings, write_token)
        return snapshots.response(snapshots.activate(request.name))

    @router.post("/import", response_model=SnapshotResponse)
    def import_snapshot(
        request: ImportRequest,
        settings: SettingsDep,
        write_token: WriteToken = None,
    ) -> SnapshotResponse:
        require_write_access(settings, write_token, import_operation=True)
        return snapshots.response(snapshots.import_request(request))

    return router


__all__ = ["snapshot_router"]
