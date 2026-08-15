from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .config import XraySettings

HydraStatus = Literal["fallback", "live", "offline"]


@dataclass(frozen=True, slots=True)
class HydraHealth:
    status: HydraStatus
    configured: bool
    database: str | None
    uri: str | None
    detail: str


def hydra_health(settings: XraySettings) -> HydraHealth:
    if not settings.hydra_configured:
        return HydraHealth(
            status="fallback",
            configured=False,
            database=None,
            uri=None,
            detail="XRAY_HYDRA_URI is not configured; using in-memory fixture analytics.",
        )
    hydra_uri = settings.hydra_uri
    if hydra_uri is None:
        raise AssertionError("hydra_configured must imply hydra_uri is set")

    try:
        from neo4j import GraphDatabase
    except ImportError:
        return HydraHealth(
            status="offline",
            configured=True,
            database=settings.hydra_database,
            uri=hydra_uri,
            detail="neo4j driver is not installed in this API environment.",
        )

    auth = None
    if settings.hydra_user is not None or settings.hydra_password is not None:
        auth = (settings.hydra_user or "", settings.hydra_password or "")

    try:
        driver = GraphDatabase.driver(hydra_uri, auth=auth)
        try:
            with driver.session(database=settings.hydra_database) as session:
                session.run("RETURN 1 AS ok").consume()
        finally:
            driver.close()
    except Exception as exc:
        return HydraHealth(
            status="offline",
            configured=True,
            database=settings.hydra_database,
            uri=hydra_uri,
            detail=f"HydraDB ping failed: {exc}",
        )

    return HydraHealth(
        status="live",
        configured=True,
        database=settings.hydra_database,
        uri=hydra_uri,
        detail="HydraDB ping succeeded.",
    )


__all__ = ["HydraHealth", "HydraStatus", "hydra_health"]
