from __future__ import annotations

import secrets

from fastapi import HTTPException

from ..config import XraySettings


def require_write_access(
    settings: XraySettings,
    supplied_token: str | None,
    *,
    import_operation: bool = False,
) -> None:
    if settings.read_only:
        raise HTTPException(status_code=403, detail="This deployment is read-only.")
    if import_operation and not settings.imports_enabled:
        raise HTTPException(
            status_code=403,
            detail="Snapshot imports are disabled; set XRAY_ENABLE_IMPORTS=true locally to opt in.",
        )
    if settings.write_token is None:
        raise HTTPException(
            status_code=403,
            detail="Mutations require XRAY_WRITE_TOKEN to be configured.",
        )
    if supplied_token is None or not secrets.compare_digest(supplied_token, settings.write_token):
        raise HTTPException(status_code=401, detail="A valid X-Xray-Write-Token is required.")


__all__ = ["require_write_access"]
