from __future__ import annotations

import json
import logging
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from xray_core.models import CanonicalBundle, LoadReport, QuerySpec, Scalar, SnapshotManifest
from xray_hydra import HydraGateway, HydraLoader
from xray_hydra.cypher import communication_paths_by_id_query
from xray_ingest.manifest import write_snapshot

from .config import XraySettings

HydraStatus = Literal["fallback", "live", "offline"]
HydraSeedStatus = Literal["complete", "partial", "fallback", "offline"]
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HydraHealth:
    status: HydraStatus
    configured: bool
    database: str | None
    uri: str | None
    detail: str
    graph_loaded: bool = False
    node_count: int | None = None
    edge_count: int | None = None


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


@dataclass(frozen=True, slots=True)
class HydraGapRow:
    phantom_key: str
    properties: dict[str, Scalar]
    predecessor_keys: tuple[str, ...]
    successor_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HydraDistanceResult:
    distances: dict[tuple[str, str], int | None]
    query: QuerySpec
    duration_ms: float
    error: str | None = None


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
                node_count = _single_count(session.run("MATCH (n) RETURN count(n) AS count").data())
                edge_count = _single_count(session.run("MATCH ()-[r]->() RETURN count(r) AS count").data())
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
        graph_loaded=bool(node_count or edge_count),
        node_count=node_count,
        edge_count=edge_count,
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
            with tempfile.TemporaryDirectory(
                prefix="xray-fixture-snapshot-", dir=snapshot_parent
            ) as temp_dir:
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


def communication_distances(
    settings: XraySettings,
    bundle: CanonicalBundle,
    pairs: tuple[tuple[str, str], ...],
    *,
    gateway: HydraGateway | None = None,
    max_len: int = 4,
) -> HydraDistanceResult | None:
    if not settings.hydra_configured or not pairs:
        return None

    created_gateway = gateway is None
    people_by_key = {node.canonical_key: node for node in bundle.nodes if node.label == "Person"}
    normalized_pairs = tuple(sorted({_normalize_pair(*pair) for pair in pairs}))
    resolved_pairs = tuple(
        pair for pair in normalized_pairs if pair[0] in people_by_key and pair[1] in people_by_key
    )
    sources = tuple(people_by_key[pair[0]].id for pair in resolved_pairs)
    targets = tuple(people_by_key[pair[1]].id for pair in resolved_pairs)
    if not resolved_pairs:
        return HydraDistanceResult(
            distances=dict.fromkeys(normalized_pairs),
            query=QuerySpec(
                name="communication_paths_by_id",
                statement="RETURN 1 AS skipped",
                parameters={},
                max_len=max_len,
                result_limit=1,
            ),
            duration_ms=0.0,
            error="No requested owner pair could be resolved to integer node ids.",
        )
    result_limit = max(1, len(normalized_pairs))
    query = communication_paths_by_id_query(
        sources,
        targets,
        max_len=max_len,
        path_count=1,
        result_limit=result_limit,
        pairwise=False,
    )
    started = time.perf_counter()
    try:
        resolved_gateway = gateway or _create_gateway(settings)
        distances: dict[tuple[str, str], int | None] = dict.fromkeys(normalized_pairs)
        for row in resolved_gateway.run(query):
            path_keys = _path_key_tuple(row.get("path"))
            if len(path_keys) < 2:
                continue
            pair = tuple(sorted((path_keys[0], path_keys[-1])))
            if pair in distances:
                distances[pair] = len(path_keys) - 1
    except Exception as exc:
        logger.exception("HydraDB communication distance query failed")
        return HydraDistanceResult(
            distances={},
            query=query,
            duration_ms=_elapsed_ms(started),
            error=str(exc),
        )
    finally:
        if (
            created_gateway
            and "resolved_gateway" in locals()
            and hasattr(resolved_gateway.driver, "close")
        ):
            resolved_gateway.driver.close()

    return HydraDistanceResult(distances=distances, query=query, duration_ms=_elapsed_ms(started))


def graph_rows(
    settings: XraySettings,
    bundle: CanonicalBundle,
    *,
    gateway: HydraGateway | None = None,
) -> HydraGraphRows | None:
    if not settings.hydra_configured:
        return None

    created_gateway = gateway is None
    try:
        resolved_gateway = gateway or _create_gateway(settings)
        people_ids = {node.id for node in bundle.nodes if node.label == "Person"}
        node_rows = resolved_gateway.run(
            QuerySpec(
                name="hydra_graph_people",
                statement=(
                    "MATCH (p:Person) "
                    "RETURN p.id AS id, p.canonical_key AS key, p.properties AS properties "
                    "ORDER BY p.canonical_key"
                ),
                parameters={},
                max_len=None,
                result_limit=None,
            )
        )
        edge_rows = resolved_gateway.run(
            QuerySpec(
                name="hydra_graph_communications",
                statement=(
                    "MATCH (s:Person)-[r:COMMUNICATES]->(t:Person) "
                    "RETURN s.id AS source_id, t.id AS target_id, "
                    "s.canonical_key AS source, t.canonical_key AS target, "
                    "r.properties AS properties "
                    "ORDER BY r.canonical_key"
                ),
                parameters={},
                max_len=None,
                result_limit=None,
            )
        )
        node_rows = [row for row in node_rows if row.get("id") in people_ids]
        edge_rows = [
            row
            for row in edge_rows
            if row.get("source_id") in people_ids and row.get("target_id") in people_ids
        ]
    except Exception:
        logger.exception("HydraDB graph rows query failed")
        return None
    finally:
        if (
            created_gateway
            and "resolved_gateway" in locals()
            and hasattr(resolved_gateway.driver, "close")
        ):
            resolved_gateway.driver.close()

    return HydraGraphRows(
        nodes=tuple(_hydra_graph_node(row) for row in node_rows),
        edges=tuple(_hydra_graph_edge(row) for row in edge_rows),
    )


def gap_rows(
    settings: XraySettings,
    bundle: CanonicalBundle,
    *,
    gateway: HydraGateway | None = None,
) -> tuple[HydraGapRow, ...] | None:
    if not settings.hydra_configured:
        return None

    created_gateway = gateway is None
    try:
        resolved_gateway = gateway or _create_gateway(settings)
        phantom_ids = {node.id for node in bundle.nodes if node.label == "Phantom"}
        rows = resolved_gateway.run(
            QuerySpec(
                name="hydra_gap_rows",
                statement=(
                    "MATCH (phantom:Phantom) "
                    "OPTIONAL MATCH (phantom)-[:PRECEDED_BY]->(predecessor) "
                    "OPTIONAL MATCH (successor)-[:PRECEDED_BY]->(phantom) "
                    "OPTIONAL MATCH (reply)-[:REPLIES_TO]->(phantom) "
                    "RETURN phantom.id AS phantom_id, phantom.canonical_key AS phantom_key, "
                    "phantom.properties AS properties, "
                    "collect(DISTINCT predecessor.canonical_key) AS predecessor_keys, "
                    "collect(DISTINCT successor.canonical_key) AS successor_keys, "
                    "collect(DISTINCT reply.canonical_key) AS reply_keys "
                    "ORDER BY phantom.canonical_key"
                ),
                parameters={},
                max_len=None,
                result_limit=None,
            )
        )
        rows = [row for row in rows if row.get("phantom_id") in phantom_ids]
    except Exception:
        logger.exception("HydraDB gap rows query failed")
        return None
    finally:
        if (
            created_gateway
            and "resolved_gateway" in locals()
            and hasattr(resolved_gateway.driver, "close")
        ):
            resolved_gateway.driver.close()

    return tuple(_hydra_gap_row(row) for row in rows)


def _hydra_gap_row(row: dict[str, object]) -> HydraGapRow:
    phantom_key = row.get("phantom_key")
    if not isinstance(phantom_key, str):
        raise ValueError("Hydra gap row is missing phantom_key")
    return HydraGapRow(
        phantom_key=phantom_key,
        properties=_properties(row.get("properties")),
        predecessor_keys=_string_tuple(row.get("predecessor_keys")),
        successor_keys=tuple(
            sorted(
                {
                    *_string_tuple(row.get("successor_keys")),
                    *_string_tuple(row.get("reply_keys")),
                }
            )
        ),
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


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(sorted(item for item in value if isinstance(item, str)))


def _single_count(rows: list[dict[str, object]]) -> int | None:
    if not rows:
        return None
    count = rows[0].get("count")
    return count if type(count) is int else None


def _normalize_pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def _path_key_tuple(path: object) -> tuple[str, ...]:
    if path is None:
        return ()
    nodes = path.get("nodes") if isinstance(path, dict) else getattr(path, "nodes", None)
    if not isinstance(nodes, (list, tuple)):
        return ()
    keys: list[str] = []
    for node in nodes:
        if isinstance(node, dict):
            value = node.get("canonical_key")
        else:
            try:
                value = node["canonical_key"]
            except Exception:
                value = None
        if not isinstance(value, str):
            return ()
        keys.append(value)
    return tuple(keys)


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


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
    "HydraDistanceResult",
    "HydraGapRow",
    "HydraGraphEdge",
    "HydraGraphNode",
    "HydraGraphRows",
    "HydraHealth",
    "HydraSeedResult",
    "HydraSeedStatus",
    "HydraStatus",
    "communication_distances",
    "gap_rows",
    "graph_rows",
    "hydra_health",
    "seed_bundle",
]
