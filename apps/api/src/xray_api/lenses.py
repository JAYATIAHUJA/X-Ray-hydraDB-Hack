from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from functools import lru_cache
from itertools import pairwise

from xray_analytics import (
    bounded_shortest_path_tallies,
    communication_graph,
    ghost_scores,
    reachable_pair_count,
    without_people,
)
from xray_analytics.analysis import BusFactorImpact, GhostScore, display_name, formal_ranks
from xray_core.models import CanonicalBundle, NodeRow, QuerySpec
from xray_core.paths import path_key_tuple
from xray_hydra import HydraGateway
from xray_hydra.cypher import communication_paths_query, sp_chain_query

from .config import XraySettings
from .hydra import open_gateway

logger = logging.getLogger(__name__)

HYDRA_GHOST_METHOD = "hydradb_mspaths_exact_betweenness"


@dataclass(frozen=True, slots=True)
class ExecutedQuery:
    text: str
    params: dict[str, object]
    max_len: int | None
    round_trips: int
    engine_ms: float


@dataclass(frozen=True, slots=True)
class WhatIfResult:
    excluded_person_keys: tuple[str, ...]
    sampled_pairs_before: int
    sampled_pairs_after: int
    pairs_lost: int
    max_len: int


@dataclass(frozen=True, slots=True)
class LiveGhostResult:
    findings: tuple[dict[str, object], ...]
    executed_query: ExecutedQuery
    error: str | None = None
    what_if: WhatIfResult | None = None
    sampled_people: int = 0


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
    exclude_person_keys: tuple[str, ...] = (),
) -> LiveGhostResult | None:
    if not settings.hydra_configured:
        return None

    people = tuple(
        sorted(
            (
                node
                for node in bundle.nodes
                if node.label == "Person" and node.properties.get("identity_status") != "unresolved"
            ),
            key=lambda n: n.id,
        )
    )
    if len(people) < 2:
        return None

    sampled = _evenly_spaced_people(people, sample_size)
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
    try:
        with open_gateway(settings, gateway) as resolved_gateway:
            rows = resolved_gateway.run(query)
    except Exception as exc:
        logger.exception("HydraDB Ghost MSpaths query failed")
        return LiveGhostResult(
            findings=(),
            executed_query=_executed(query, started),
            error=str(exc),
        )

    graph = _communication_graph_from_paths(rows)
    findings = _ghost_findings_from_graph(
        bundle,
        graph,
        max_len=max_len,
        exclude_person_keys=exclude_person_keys,
    )
    what_if = (
        _what_if_from_graph(graph, exclude_person_keys, max_len=max_len)
        if exclude_person_keys
        else None
    )

    return LiveGhostResult(
        findings=findings,
        executed_query=_executed(query, started),
        what_if=what_if,
        sampled_people=len(sampled),
    )


def _evenly_spaced_people(people: tuple[NodeRow, ...], sample_size: int) -> tuple[NodeRow, ...]:
    """Select deterministic endpoints across the full canonical ordering."""
    limit = min(len(people), sample_size)
    if limit <= 0:
        return ()
    if limit == len(people):
        return people
    if limit == 1:
        return (people[0],)
    last = len(people) - 1
    return tuple(people[round(index * last / (limit - 1))] for index in range(limit))


def _communication_graph_from_paths(rows: list[dict[str, object]]) -> dict[str, dict[str, int]]:
    graph: dict[str, dict[str, int]] = {}
    for row in rows:
        keys = path_key_tuple(row.get("path"))
        for left, right in pairwise(keys):
            if left == right:
                continue
            graph.setdefault(left, {})[right] = 1
            graph.setdefault(right, {})[left] = 1
        for key in keys:
            graph.setdefault(key, {})
    return graph


def _ghost_findings_from_graph(
    bundle: CanonicalBundle,
    graph: dict[str, dict[str, int]],
    *,
    max_len: int,
    exclude_person_keys: tuple[str, ...],
) -> tuple[dict[str, object], ...]:
    excluded = set(exclude_person_keys)
    scored_graph = {
        node: {
            neighbor: weight for neighbor, weight in neighbors.items() if neighbor not in excluded
        }
        for node, neighbors in graph.items()
        if node not in excluded
    }
    people_by_key = {
        node.canonical_key: node
        for node in bundle.nodes
        if node.label == "Person" and node.properties.get("identity_status") != "unresolved"
    }
    person_keys = sorted(key for key in scored_graph if key in people_by_key)
    if len(person_keys) < 2:
        return ()

    import networkx as nx

    reference: nx.Graph[str] = nx.Graph()
    reference.add_nodes_from(person_keys)
    reference.add_edges_from(
        (source, target)
        for source, neighbors in scored_graph.items()
        for target in neighbors
        if source < target and source in people_by_key and target in people_by_key
    )
    centrality = nx.betweenness_centrality(reference, normalized=True, weight=None)
    structural_order = sorted(person_keys, key=lambda key: (-centrality[key], key))
    structural_rank = {key: index for index, key in enumerate(structural_order, start=1)}
    people_nodes = tuple(people_by_key[key] for key in person_keys)
    formal_rank = formal_ranks(people_nodes)

    findings: list[dict[str, object]] = []
    for index, person_key in enumerate(structural_order):
        node = people_by_key[person_key]
        role_rank = node.properties.get("role_rank")
        score = GhostScore(
            person_key=person_key,
            display_name=display_name(node),
            role_rank=role_rank if type(role_rank) is int else 0,
            structural_rank=structural_rank[person_key],
            formal_rank=formal_rank[person_key],
            rank_gap=formal_rank[person_key] - structural_rank[person_key],
            sampled_centrality=float(centrality[person_key]),
            communication_degree=len(scored_graph.get(person_key, {})),
            centrality_method=HYDRA_GHOST_METHOD,
        )
        impact = None
        if index < 10:
            before = reachable_pair_count(scored_graph, max_len=max_len)
            reduced = {
                node_key: {
                    neighbor: weight
                    for neighbor, weight in neighbors.items()
                    if neighbor != person_key
                }
                for node_key, neighbors in scored_graph.items()
                if node_key != person_key
            }
            after = reachable_pair_count(reduced, max_len=max_len)
            impact = asdict(
                BusFactorImpact(
                    person_key=person_key,
                    reachable_pairs_before=before,
                    pairs_lost_without_person=before - after,
                    max_len=max_len,
                )
            )
        findings.append({**asdict(score), "removal_impact": impact})
    return tuple(findings)


def _what_if_from_graph(
    graph: dict[str, dict[str, int]],
    exclude_person_keys: tuple[str, ...],
    *,
    max_len: int,
) -> WhatIfResult:
    excluded = tuple(sorted(set(exclude_person_keys)))
    before = reachable_pair_count(graph, max_len=max_len, excluding=excluded)
    reduced = {
        node: {
            neighbor: weight for neighbor, weight in neighbors.items() if neighbor not in excluded
        }
        for node, neighbors in graph.items()
        if node not in excluded
    }
    after = reachable_pair_count(reduced, max_len=max_len)
    return WhatIfResult(
        excluded_person_keys=excluded,
        sampled_pairs_before=before,
        sampled_pairs_after=after,
        pairs_lost=before - after,
        max_len=max_len,
    )


def fixture_ghost_findings(
    bundle: CanonicalBundle,
    *,
    max_len: int = 4,
    exclude_person_keys: tuple[str, ...] = (),
) -> tuple[dict[str, object], ...]:
    """In-memory Ghost findings; excluded people are removed from the graph before scoring."""
    findings = []
    scored_bundle = without_people(bundle, exclude_person_keys) if exclude_person_keys else bundle
    graph = communication_graph(scored_bundle)
    for index, score in enumerate(ghost_scores(scored_bundle, max_len=max_len)):
        impact = None
        if index < 10:
            before = reachable_pair_count(graph, max_len=max_len)
            reduced = {
                node: {
                    neighbor: weight
                    for neighbor, weight in neighbors.items()
                    if neighbor != score.person_key
                }
                for node, neighbors in graph.items()
                if node != score.person_key
            }
            after = reachable_pair_count(reduced, max_len=max_len)
            impact = asdict(
                BusFactorImpact(
                    person_key=score.person_key,
                    reachable_pairs_before=before,
                    pairs_lost_without_person=before - after,
                    max_len=max_len,
                )
            )
        findings.append({**asdict(score), "removal_impact": impact})
    return tuple(findings)


def fixture_what_if(
    bundle: CanonicalBundle,
    exclude_person_keys: tuple[str, ...],
    *,
    max_len: int = 4,
) -> WhatIfResult:
    """Count bounded-reachable person pairs before and after removing people (in memory)."""
    excluded = tuple(sorted(set(exclude_person_keys)))
    before = reachable_pair_count(communication_graph(bundle), max_len=max_len, excluding=excluded)
    reduced = without_people(bundle, excluded)
    after = reachable_pair_count(communication_graph(reduced), max_len=max_len)
    return WhatIfResult(
        excluded_person_keys=excluded,
        sampled_pairs_before=before,
        sampled_pairs_after=after,
        pairs_lost=before - after,
        max_len=max_len,
    )


def client_ghost_baseline_ms(bundle: CanonicalBundle, *, max_len: int = 4) -> float:
    """Wall-clock ms for the in-process bounded-BFS Ghost tally over the whole bundle.

    Measured once per bundle on the uncached path so the API can show the engine
    round trip next to the client-side equivalent honestly.
    """
    graph = communication_graph(bundle)
    adjacency = tuple((node, tuple(sorted(neighbors))) for node, neighbors in sorted(graph.items()))
    return _client_ghost_baseline_cached(adjacency, max_len)


@lru_cache(maxsize=32)
def _client_ghost_baseline_cached(
    adjacency: tuple[tuple[str, tuple[str, ...]], ...], max_len: int
) -> float:
    graph = {node: dict.fromkeys(neighbors, 1) for node, neighbors in adjacency}
    started = time.perf_counter()
    bounded_shortest_path_tallies(graph, sorted(graph), max_len)
    return (time.perf_counter() - started) * 1000


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
    try:
        with open_gateway(settings, gateway) as resolved_gateway:
            rows = resolved_gateway.run(query)
    except Exception as exc:
        logger.exception("HydraDB Gap SPpaths query failed")
        return LiveGapChainResult(
            node_keys=(),
            executed_query=_executed(query, started),
            error=str(exc),
        )

    node_keys: tuple[str, ...] = ()
    if rows:
        node_keys = path_key_tuple(rows[0].get("path"))
    return LiveGapChainResult(node_keys=node_keys, executed_query=_executed(query, started))


def _executed(query: QuerySpec, started: float) -> ExecutedQuery:
    return ExecutedQuery(
        text=query.statement,
        params=dict(query.parameters),
        max_len=query.max_len,
        round_trips=1,
        engine_ms=(time.perf_counter() - started) * 1000,
    )


__all__ = [
    "ExecutedQuery",
    "LiveGapChainResult",
    "LiveGhostResult",
    "fixture_ghost_findings",
    "live_gap_chain",
    "live_ghost_findings",
]
