from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import asdict, dataclass

from xray_analytics import GhostScore, bus_factor_impact, communication_graph, ghost_scores
from xray_core.models import CanonicalBundle, NodeRow, QuerySpec
from xray_hydra import HydraGateway
from xray_hydra.cypher import communication_paths_query, sp_chain_query

from .config import XraySettings

logger = logging.getLogger(__name__)
_FIXTURE_GHOST_CACHE: dict[tuple[int, int], tuple[dict[str, object], ...]] = {}


@dataclass(frozen=True, slots=True)
class ExecutedQuery:
    text: str
    params: dict[str, object]
    max_len: int | None
    round_trips: int
    engine_ms: float


@dataclass(frozen=True, slots=True)
class LiveGhostResult:
    findings: tuple[dict[str, object], ...]
    executed_query: ExecutedQuery
    error: str | None = None


@dataclass(frozen=True, slots=True)
class LiveGapChainResult:
    node_keys: tuple[str, ...]
    executed_query: ExecutedQuery
    error: str | None = None


def live_ghost_findings(
    settings: XraySettings,
    bundle: CanonicalBundle,
    *,
    gateway: HydraGateway | None = None,
    sample_size: int = 150,
    max_len: int = 4,
    path_count: int = 3,
) -> LiveGhostResult | None:
    if not settings.hydra_configured:
        return None

    people = tuple(
        sorted((node for node in bundle.nodes if node.label == "Person"), key=lambda n: n.id)
    )
    if len(people) < 2:
        return None

    sampled = people[: min(len(people), sample_size)]
    sampled_path_keys = tuple(node.path_key for node in sampled)
    result_limit = max(1, len(sampled_path_keys) * len(sampled_path_keys) * path_count)
    query = communication_paths_query(
        sampled_path_keys,
        sampled_path_keys,
        max_len=max_len,
        path_count=path_count,
        result_limit=result_limit,
        pairwise=False,
    )
    started = time.perf_counter()
    created_gateway = gateway is None

    try:
        resolved_gateway = gateway or _create_gateway(settings)
        rows = resolved_gateway.run(query)
    except Exception as exc:
        logger.exception("HydraDB Ghost MSpaths query failed")
        return LiveGhostResult(
            findings=(),
            executed_query=_executed(query, started),
            error=str(exc),
        )
    finally:
        if (
            created_gateway
            and "resolved_gateway" in locals()
            and hasattr(resolved_gateway.driver, "close")
        ):
            resolved_gateway.driver.close()

    paths = tuple(path for row in rows if (path := _path_key_tuple(row.get("path"))))
    sampled_pairs = {
        _normalize_pair(path[0], path[-1])
        for path in paths
        if len(path) >= 2 and path[0] != path[-1]
    }
    denominator = float(len(sampled_pairs) or 1)
    tallies: dict[str, float] = defaultdict(float)
    for path in paths:
        for intermediate in path[1:-1]:
            tallies[intermediate] += 1.0

    graph = communication_graph(bundle)
    formal_rank = _formal_rank(people)
    structural_order = sorted(
        (node.canonical_key for node in people),
        key=lambda key: (-(tallies[key] / denominator), key),
    )
    structural_rank = {key: index for index, key in enumerate(structural_order, start=1)}
    nodes_by_key = {node.canonical_key: node for node in people}
    findings = []
    top_impact_keys = set(structural_order[:10])
    for key in structural_order:
        node = nodes_by_key[key]
        score = GhostScore(
            person_key=key,
            display_name=_display_name(node),
            role_rank=_role_rank(node),
            structural_rank=structural_rank[key],
            formal_rank=formal_rank[key],
            rank_gap=formal_rank[key] - structural_rank[key],
            sampled_centrality=tallies[key] / denominator,
            communication_degree=len(graph.get(key, {})),
        )
        removal_impact = None
        if key in top_impact_keys:
            removal_impact = asdict(bus_factor_impact(bundle, key, max_len=max_len, graph=graph))
            removal_impact["sampled_pairs_lost_without_person"] = sum(
                1 for path in paths if key in path[1:-1] and path[0] != key and path[-1] != key
            )
            removal_impact["sampled_pairs_observed"] = len(sampled_pairs)
        findings.append({**asdict(score), "removal_impact": removal_impact})

    return LiveGhostResult(findings=tuple(findings), executed_query=_executed(query, started))


def fixture_ghost_findings(
    bundle: CanonicalBundle, *, max_len: int = 4
) -> tuple[dict[str, object], ...]:
    cache_key = (id(bundle), max_len)
    cached = _FIXTURE_GHOST_CACHE.get(cache_key)
    if cached is not None:
        return cached

    findings = []
    graph = communication_graph(bundle)
    for index, score in enumerate(ghost_scores(bundle, max_len=max_len)):
        impact = (
            asdict(bus_factor_impact(bundle, score.person_key, max_len=max_len, graph=graph))
            if index < 10
            else None
        )
        findings.append({**asdict(score), "removal_impact": impact})
    result = tuple(findings)
    _FIXTURE_GHOST_CACHE[cache_key] = result
    return result


def live_gap_chain(
    settings: XraySettings,
    bundle: CanonicalBundle,
    *,
    source_artifact_key: str,
    target_artifact_key: str,
    gateway: HydraGateway | None = None,
    max_len: int = 8,
) -> LiveGapChainResult | None:
    if not settings.hydra_configured:
        return None

    nodes = {node.canonical_key: node for node in bundle.nodes}
    source = nodes.get(source_artifact_key)
    target = nodes.get(target_artifact_key)
    if source is None or target is None:
        return None

    query = sp_chain_query(source.id, target.id, max_len=max_len, result_limit=20)
    started = time.perf_counter()
    created_gateway = gateway is None
    try:
        resolved_gateway = gateway or _create_gateway(settings)
        rows = resolved_gateway.run(query)
    except Exception as exc:
        logger.exception("HydraDB Gap SPpaths query failed")
        return LiveGapChainResult(
            node_keys=(),
            executed_query=_executed(query, started),
            error=str(exc),
        )
    finally:
        if (
            created_gateway
            and "resolved_gateway" in locals()
            and hasattr(resolved_gateway.driver, "close")
        ):
            resolved_gateway.driver.close()

    node_keys: tuple[str, ...] = ()
    if rows:
        node_keys = _path_key_tuple(rows[0].get("path"))
    return LiveGapChainResult(node_keys=node_keys, executed_query=_executed(query, started))


def _formal_rank(people: tuple[NodeRow, ...]) -> dict[str, int]:
    ordered = sorted(people, key=lambda node: (-_role_rank(node), node.canonical_key))
    return {node.canonical_key: index for index, node in enumerate(ordered, start=1)}


def _display_name(node: NodeRow) -> str:
    value = node.properties.get("display_name") or node.properties.get("handle")
    return value if isinstance(value, str) else node.canonical_key


def _role_rank(node: NodeRow) -> int:
    value = node.properties.get("role_rank")
    return value if type(value) is int else 0


def _path_key_tuple(path: object) -> tuple[str, ...]:
    if path is None:
        return ()
    if isinstance(path, (list, tuple)):
        nodes: tuple[object, ...] = tuple(
            item
            for item in path
            if isinstance(item, dict)
            or (not isinstance(item, str) and hasattr(item, "__getitem__"))
        )
    else:
        raw_nodes = path.get("nodes") if isinstance(path, dict) else getattr(path, "nodes", None)
        if not isinstance(raw_nodes, (list, tuple)):
            return ()
        nodes = tuple(raw_nodes)
    keys: list[str] = []
    for node in nodes:
        value = _node_value(node, "canonical_key")
        if not isinstance(value, str):
            value = _node_value(node, "path_key")
        if not isinstance(value, str):
            return ()
        keys.append(value)
    return tuple(keys)


def _node_value(node: object, key: str) -> object:
    if isinstance(node, dict):
        return node.get(key)
    try:
        return node[key]  # type: ignore[index]
    except Exception:
        return None


def _normalize_pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def _executed(query: QuerySpec, started: float) -> ExecutedQuery:
    return ExecutedQuery(
        text=query.statement,
        params=dict(query.parameters),
        max_len=query.max_len,
        round_trips=1,
        engine_ms=(time.perf_counter() - started) * 1000,
    )


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
    "ExecutedQuery",
    "LiveGapChainResult",
    "LiveGhostResult",
    "fixture_ghost_findings",
    "live_gap_chain",
    "live_ghost_findings",
]
