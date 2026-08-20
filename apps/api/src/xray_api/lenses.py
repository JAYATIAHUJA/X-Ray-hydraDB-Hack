from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from functools import lru_cache

from xray_analytics import (
    bounded_shortest_path_tallies,
    bus_factor_impact,
    communication_graph,
    ghost_scores,
    reachable_pair_count,
    without_people,
)
from xray_core.models import CanonicalBundle, NodeRow, QuerySpec
from xray_core.paths import path_key_tuple
from xray_hydra import HydraGateway
from xray_hydra.cypher import communication_paths_query, sp_chain_query

from .config import XraySettings
from .hydra import open_gateway

logger = logging.getLogger(__name__)


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
                if node.label == "Person"
                and node.properties.get("identity_status") != "unresolved"
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
            resolved_gateway.run(query)
    except Exception as exc:
        logger.exception("HydraDB Ghost MSpaths query failed")
        return LiveGhostResult(
            findings=(),
            executed_query=_executed(query, started),
            error=str(exc),
        )

    # MSpaths remains the engine traversal and timing measurement. Ranking is computed
    # over the full immutable bundle so a truncated path result cannot bias people who
    # were not selected as endpoints. Counterfactuals rebuild the graph without the
    # excluded nodes, allowing alternate paths to be discovered.
    findings = fixture_ghost_findings(
        bundle,
        max_len=max_len,
        exclude_person_keys=exclude_person_keys,
    )
    what_if = (
        fixture_what_if(bundle, exclude_person_keys, max_len=max_len)
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
        impact = (
            asdict(bus_factor_impact(scored_bundle, score.person_key, max_len=max_len, graph=graph))
            if index < 10
            else None
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
