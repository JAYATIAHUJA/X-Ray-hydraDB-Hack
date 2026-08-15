from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from xray_core.models import CanonicalBundle, LoadReport, QuerySpec, Scalar, SnapshotManifest
from xray_hydra import HydraGateway, HydraLoader
from xray_ingest.manifest import write_snapshot

from .config import XraySettings

HydraStatus = Literal["fallback", "live", "offline"]
HydraSeedStatus = Literal["complete", "partial", "fallback", "offline"]


@dataclass(frozen=True, slots=True)
class HydraHealth:
    status: HydraStatus
    configured: bool
    database: str | None
    uri: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class HydraSeedResult:
    status: HydraSeedStatus
    hydra: HydraHealth
    report: LoadReport | None
    detail: str


@dataclass(frozen=True, slots=True)
class HydraGraphNode:
    key: str
    properties: dict[str, Scalar]


@dataclass(frozen=True, slots=True)
class HydraGraphEdge:
    source: str
    target: str
    weight: float


@dataclass(frozen=True, slots=True)
class HydraGraphRows:
    nodes: tuple[HydraGraphNode, ...]
    edges: tuple[HydraGraphEdge, ...]


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


def seed_bundle(
    settings: XraySettings,
    bundle: CanonicalBundle,
    *,
    gateway: HydraGateway | None = None,
    loader_factory: Callable[[HydraGateway], HydraLoader] = HydraLoader,
    snapshot_dir: Path | None = None,
    snapshot_parent: Path | None = None,
    snapshot_writer: Callable[[CanonicalBundle, Path], SnapshotManifest] = write_snapshot,
) -> HydraSeedResult:
    if not settings.hydra_configured:
        health = hydra_health(settings)
        return HydraSeedResult(
            status="fallback",
            hydra=health,
            report=None,
            detail="HydraDB is not configured; fixture seed was skipped.",
        )

    created_gateway = gateway is None
    try:
        resolved_gateway = gateway or _create_gateway(settings)
    except Exception as exc:
        hydra_uri = settings.hydra_uri or ""
        return HydraSeedResult(
            status="offline",
            hydra=HydraHealth(
                status="offline",
                configured=True,
                database=settings.hydra_database,
                uri=hydra_uri,
                detail=f"HydraDB gateway creation failed: {exc}",
            ),
            report=None,
            detail="HydraDB fixture seed could not start.",
        )

    try:
        if snapshot_dir is not None:
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            manifest = snapshot_writer(bundle, snapshot_dir)
            report = loader_factory(resolved_gateway).load(snapshot_dir, manifest)
        elif snapshot_parent is not None:
            snapshot_parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="xray-fixture-snapshot-", dir=snapshot_parent) as temp_dir:
                generated_snapshot_dir = Path(temp_dir)
                manifest = snapshot_writer(bundle, generated_snapshot_dir)
                report = loader_factory(resolved_gateway).load(generated_snapshot_dir, manifest)
        else:
            with tempfile.TemporaryDirectory(prefix="xray-fixture-snapshot-") as temp_dir:
                generated_snapshot_dir = Path(temp_dir)
                manifest = snapshot_writer(bundle, generated_snapshot_dir)
                report = loader_factory(resolved_gateway).load(generated_snapshot_dir, manifest)
    finally:
        if created_gateway and hasattr(resolved_gateway.driver, "close"):
            resolved_gateway.driver.close()

    status: HydraSeedStatus = "partial" if report.failed_batches else "complete"
    return HydraSeedResult(
        status=status,
        hydra=HydraHealth(
            status="live",
            configured=True,
            database=settings.hydra_database,
            uri=settings.hydra_uri,
            detail="HydraDB fixture seed executed.",
        ),
        report=report,
        detail=(
            "HydraDB fixture seed completed."
            if status == "complete"
            else "HydraDB fixture seed completed with failed batches."
        ),
    )


def graph_rows(
    settings: XraySettings,
    dataset_id: str,
    *,
    gateway: HydraGateway | None = None,
) -> HydraGraphRows | None:
    if not settings.hydra_configured:
        return None

    created_gateway = gateway is None
    try:
        resolved_gateway = gateway or _create_gateway(settings)
        node_rows = resolved_gateway.run(
            QuerySpec(
                name="hydra_graph_people",
                statement=(
                    "MATCH (p:Person {dataset_id: $dataset_id}) "
                    "RETURN p.canonical_key AS key, p.properties AS properties "
                    "ORDER BY p.canonical_key"
                ),
                parameters={"dataset_id": dataset_id},
                max_len=None,
                result_limit=None,
            )
        )
        edge_rows = resolved_gateway.run(
            QuerySpec(
                name="hydra_graph_communications",
                statement=(
                    "MATCH (s:Person {dataset_id: $dataset_id})-[r:COMMUNICATES]->"
                    "(t:Person {dataset_id: $dataset_id}) "
                    "RETURN s.canonical_key AS source, t.canonical_key AS target, "
                    "r.properties AS properties "
                    "ORDER BY r.canonical_key"
                ),
                parameters={"dataset_id": dataset_id},
                max_len=None,
                result_limit=None,
            )
        )
    except Exception:
        return None
    finally:
        if created_gateway and "resolved_gateway" in locals() and hasattr(resolved_gateway.driver, "close"):
            resolved_gateway.driver.close()

    return HydraGraphRows(
        nodes=tuple(_hydra_graph_node(row) for row in node_rows),
        edges=tuple(_hydra_graph_edge(row) for row in edge_rows),
    )


def _hydra_graph_node(row: dict[str, object]) -> HydraGraphNode:
    key = row.get("key")
    if not isinstance(key, str):
        raise ValueError("Hydra graph node row is missing key")
    return HydraGraphNode(key=key, properties=_properties(row.get("properties")))


def _hydra_graph_edge(row: dict[str, object]) -> HydraGraphEdge:
    source = row.get("source")
    target = row.get("target")
    if not isinstance(source, str) or not isinstance(target, str):
        raise ValueError("Hydra graph edge row is missing endpoints")
    properties = _properties(row.get("properties"))
    weight = properties.get("weight", 0)
    if type(weight) not in {int, float}:
        weight = 0
    return HydraGraphEdge(source=source, target=target, weight=float(weight))


def _properties(value: object) -> dict[str, Scalar]:
    if isinstance(value, str):
        parsed = json.loads(value)
    else:
        parsed = value
    if not isinstance(parsed, dict):
        raise ValueError("Hydra properties must be an object")
    properties: dict[str, Scalar] = {}
    for key, item in parsed.items():
        if isinstance(key, str) and type(item) in {int, float, bool, str}:
            properties[key] = item
    return properties


def _create_gateway(settings: XraySettings) -> HydraGateway:
    hydra_uri = settings.hydra_uri
    if hydra_uri is None:
        raise AssertionError("hydra_configured must imply hydra_uri is set")

    from neo4j import GraphDatabase

    auth = None
    if settings.hydra_user is not None or settings.hydra_password is not None:
        auth = (settings.hydra_user or "", settings.hydra_password or "")

    return HydraGateway(GraphDatabase.driver(hydra_uri, auth=auth))


__all__ = [
    "HydraGraphEdge",
    "HydraGraphNode",
    "HydraGraphRows",
    "HydraHealth",
    "HydraSeedResult",
    "HydraSeedStatus",
    "HydraStatus",
    "graph_rows",
    "hydra_health",
    "seed_bundle",
]
