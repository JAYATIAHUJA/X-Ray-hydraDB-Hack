from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import asdict, dataclass

from xray_analytics import (
    GhostScore,
    bounded_shortest_path_tallies,
    bus_factor_impact,
    communication_graph,
    display_name,
    formal_ranks,
    ghost_scores,
    reachable_pair_count,
    role_rank,
    without_people,
)
from xray_core.models import CanonicalBundle, QuerySpec
from xray_core.paths import normalize_pair, path_key_tuple
from xray_hydra import HydraGateway
from xray_hydra.cypher import communication_paths_query, sp_chain_query

from .config import XraySettings
from .hydra import open_gateway

logger = logging.getLogger(__name__)
_FIXTURE_GHOST_CACHE: dict[tuple[int, int, tuple[str, ...]], tuple[dict[str, object], ...]] = {}


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

    all_paths = tuple(path for row in rows if (path := path_key_tuple(row.get("path"))))
    excluded = frozenset(exclude_person_keys)
    # What-if removal (spec §5.1): drop every returned path that touches an excluded
    # person, then compare how many sampled pairs still have a bounded path.
    paths = (
        tuple(path for path in all_paths if excluded.isdisjoint(path)) if excluded else all_paths
    )
    pairs_before = {
        normalize_pair(path[0], path[-1])
        for path in all_paths
        if len(path) >= 2 and path[0] != path[-1]
    }
    sampled_pairs = {
        normalize_pair(path[0], path[-1])
        for path in paths
        if len(path) >= 2 and path[0] != path[-1]
    }
    what_if = (
        WhatIfResult(
            excluded_person_keys=tuple(sorted(excluded)),
            sampled_pairs_before=len(pairs_before),
            sampled_pairs_after=len(sampled_pairs),
            pairs_lost=len(pairs_before) - len(sampled_pairs),
            max_len=max_len,
        )
        if excluded
        else None
    )
    denominator = float(len(sampled_pairs) or 1)
    tallies: dict[str, float] = defaultdict(float)
    for path in paths:
        for intermediate in path[1:-1]:
            tallies[intermediate] += 1.0

    graph = communication_graph(bundle)
    formal_rank = formal_ranks(people)
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
            display_name=display_name(node),
            role_rank=role_rank(node),
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

    return LiveGhostResult(
        findings=tuple(findings),
        executed_query=_executed(query, started),
        what_if=what_if,
        sampled_people=len(sampled),
    )


def fixture_ghost_findings(
    bundle: CanonicalBundle,
    *,
    max_len: int = 4,
    exclude_person_keys: tuple[str, ...] = (),
) -> tuple[dict[str, object], ...]:
    """In-memory Ghost findings; excluded people are removed from the graph before scoring."""
    cache_key = (id(bundle), max_len, tuple(sorted(exclude_person_keys)))
    cached = _FIXTURE_GHOST_CACHE.get(cache_key)
    if cached is not None:
        return cached

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
    result = tuple(findings)
    _FIXTURE_GHOST_CACHE[cache_key] = result
    return result


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


_CLIENT_BASELINE_MS: dict[tuple[int, int], float] = {}


def client_ghost_baseline_ms(bundle: CanonicalBundle, *, max_len: int = 4) -> float:
    """Wall-clock ms for the in-process bounded-BFS Ghost tally over the whole bundle.

    Measured once per bundle on the uncached path so the API can show the engine
    round trip next to the client-side equivalent honestly.
    """
    key = (id(bundle), max_len)
    cached = _CLIENT_BASELINE_MS.get(key)
    if cached is not None:
        return cached
    graph = communication_graph(bundle)
    person_keys = sorted(graph)
    started = time.perf_counter()
    bounded_shortest_path_tallies(graph, person_keys, max_len)
    elapsed = (time.perf_counter() - started) * 1000
    _CLIENT_BASELINE_MS[key] = elapsed
    return elapsed


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
