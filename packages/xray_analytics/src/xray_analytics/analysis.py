from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from xray_core.models import CanonicalBundle, EdgeRow, NodeRow


@dataclass(frozen=True, slots=True)
class GhostScore:
    person_key: str
    display_name: str
    role_rank: int
    structural_rank: int
    formal_rank: int
    rank_gap: int
    sampled_centrality: float
    communication_degree: int


@dataclass(frozen=True, slots=True)
class BusFactorImpact:
    person_key: str
    reachable_pairs_before: int
    pairs_lost_without_person: int
    max_len: int


@dataclass(frozen=True, slots=True)
class FaultlineFinding:
    source_module_key: str
    target_module_key: str
    source_owner_key: str
    target_owner_key: str
    dependency_weight: int
    source_owner_confidence: int
    target_owner_confidence: int
    communication_distance: int | None
    tier: str
    severity: float


@dataclass(frozen=True, slots=True)
class GapFinding:
    phantom_key: str
    expected_kind: str
    reason: str
    inferred_epoch: int | None
    predecessor_keys: tuple[str, ...]
    successor_keys: tuple[str, ...]


def _nodes_by_id(bundle: CanonicalBundle) -> dict[int, NodeRow]:
    return {node.id: node for node in bundle.nodes}


def _nodes_by_key(bundle: CanonicalBundle) -> dict[str, NodeRow]:
    return {node.canonical_key: node for node in bundle.nodes}


def _person_nodes(bundle: CanonicalBundle) -> tuple[NodeRow, ...]:
    return tuple(
        sorted((node for node in bundle.nodes if node.label == "Person"), key=lambda n: n.id)
    )


def display_name(node: NodeRow) -> str:
    value = node.properties.get("display_name") or node.properties.get("handle")
    return value if isinstance(value, str) else node.canonical_key


def _int_property(edge: EdgeRow, key: str, default: int) -> int:
    value = edge.properties.get(key)
    return value if type(value) is int else default


type CommunicationGraph = dict[str, dict[str, int]]

# Faultline tiers. Owners with no bounded communication path carry full risk;
# owners linked only through intermediaries (distance >= WEAK_DISTANCE) carry
# half; a direct or 2-hop link is coordinated and is not a finding.
TIER_NO_PATH = "no_path"
TIER_WEAK = "weak_coordination"
TIER_COORDINATED = "coordinated"
WEAK_DISTANCE = 3
TIER_RISK = {TIER_NO_PATH: 1.0, TIER_WEAK: 0.5, TIER_COORDINATED: 0.0}


def faultline_tier(distance: int | None) -> tuple[str, float]:
    """Return the (tier, risk) for an owner-to-owner communication distance.

    This is the single source of truth for tiering; both the in-memory analysis
    and the live HydraDB distance path call it.
    """
    if distance is None:
        return TIER_NO_PATH, TIER_RISK[TIER_NO_PATH]
    if distance >= WEAK_DISTANCE:
        return TIER_WEAK, TIER_RISK[TIER_WEAK]
    return TIER_COORDINATED, TIER_RISK[TIER_COORDINATED]


def formal_ranks(people: tuple[NodeRow, ...]) -> dict[str, int]:
    """Rank people by formal seniority (higher role_rank first, then key)."""
    ordered = sorted(people, key=lambda node: (-role_rank(node), node.canonical_key))
    return {node.canonical_key: index for index, node in enumerate(ordered, start=1)}


_REACHABLE_WITHIN_CACHE: dict[tuple[int, str, int], frozenset[str]] = {}
_GHOST_SCORE_CACHE: dict[tuple[int, int], tuple[GhostScore, ...]] = {}


def communication_graph(bundle: CanonicalBundle) -> CommunicationGraph:
    graph: CommunicationGraph = {}
    nodes = _nodes_by_id(bundle)
    for person in _person_nodes(bundle):
        graph[person.canonical_key] = {}
    for edge in bundle.edges:
        if edge.rel_type != "COMMUNICATES":
            continue
        source = nodes[edge.source_id]
        target = nodes[edge.target_id]
        weight = _int_property(edge, "weight", 1)
        graph[source.canonical_key][target.canonical_key] = weight
        graph[target.canonical_key][source.canonical_key] = weight
    return graph


def ghost_scores(bundle: CanonicalBundle, *, max_len: int = 4) -> tuple[GhostScore, ...]:
    if max_len <= 0:
        raise ValueError("max_len must be positive")
    cache_key = (id(bundle), max_len)
    cached = _GHOST_SCORE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    graph = communication_graph(bundle)
    people = _person_nodes(bundle)
    person_keys = [person.canonical_key for person in people]
    tallies, sampled_pairs = _bounded_shortest_path_tallies(graph, person_keys, max_len)

    denominator = float(sampled_pairs or 1)
    centrality = {key: tallies[key] / denominator for key in person_keys}
    structural_order = sorted(person_keys, key=lambda key: (-centrality[key], key))
    structural_rank = {key: index for index, key in enumerate(structural_order, start=1)}
    formal_rank = formal_ranks(people)

    scores = [
        GhostScore(
            person_key=node.canonical_key,
            display_name=display_name(node),
            role_rank=role_rank(node),
            structural_rank=structural_rank[node.canonical_key],
            formal_rank=formal_rank[node.canonical_key],
            rank_gap=formal_rank[node.canonical_key] - structural_rank[node.canonical_key],
            sampled_centrality=centrality[node.canonical_key],
            communication_degree=len(graph[node.canonical_key]),
        )
        for node in people
    ]
    result = tuple(sorted(scores, key=lambda score: (-score.sampled_centrality, score.person_key)))
    _GHOST_SCORE_CACHE[cache_key] = result
    return result


def bus_factor_impact(
    bundle: CanonicalBundle,
    person_key: str,
    *,
    max_len: int = 4,
    graph: CommunicationGraph | None = None,
) -> BusFactorImpact:
    if max_len <= 0:
        raise ValueError("max_len must be positive")

    graph = communication_graph(bundle) if graph is None else graph
    if person_key not in graph:
        raise ValueError(f"unknown person_key {person_key!r}")

    remaining_people = tuple(node for node in graph if node != person_key)
    reduced_graph = _without_node(graph, person_key)
    before = _reachable_pair_count(graph, remaining_people, max_len)
    after = _reachable_pair_count(reduced_graph, remaining_people, max_len, use_cache=False)
    return BusFactorImpact(
        person_key=person_key,
        reachable_pairs_before=before,
        pairs_lost_without_person=before - after,
        max_len=max_len,
    )


def faultlines(
    bundle: CanonicalBundle,
    *,
    max_len: int = 4,
    min_owner_confidence: int = 50,
) -> tuple[FaultlineFinding, ...]:
    if max_len <= 0:
        raise ValueError("max_len must be positive")
    if not 0 <= min_owner_confidence <= 100:
        raise ValueError("min_owner_confidence must be between 0 and 100")

    nodes = _nodes_by_id(bundle)
    owners = _module_owners(bundle, min_owner_confidence=min_owner_confidence)
    graph = communication_graph(bundle)
    findings: list[FaultlineFinding] = []

    for edge in bundle.edges:
        if edge.rel_type != "DEPENDS_ON":
            continue
        source_module = nodes[edge.source_id].canonical_key
        target_module = nodes[edge.target_id].canonical_key
        source_owners = owners.get(source_module, ())
        target_owners = owners.get(target_module, ())
        for source_owner_key, source_confidence in source_owners:
            for target_owner_key, target_confidence in target_owners:
                distance = _bounded_distance(graph, source_owner_key, target_owner_key, max_len)
                tier, risk = faultline_tier(distance)
                if risk == 0.0:
                    continue
                dependency_weight = _int_property(edge, "weight", 1)
                findings.append(
                    FaultlineFinding(
                        source_module_key=source_module,
                        target_module_key=target_module,
                        source_owner_key=source_owner_key,
                        target_owner_key=target_owner_key,
                        dependency_weight=dependency_weight,
                        source_owner_confidence=source_confidence,
                        target_owner_confidence=target_confidence,
                        communication_distance=distance,
                        tier=tier,
                        severity=dependency_weight * risk,
                    )
                )
    return tuple(
        sorted(
            findings,
            key=lambda item: (-item.severity, item.source_module_key, item.target_module_key),
        )
    )


def gap_findings(bundle: CanonicalBundle) -> tuple[GapFinding, ...]:
    nodes = _nodes_by_id(bundle)
    predecessors: dict[str, list[str]] = defaultdict(list)
    successors: dict[str, list[str]] = defaultdict(list)
    for edge in bundle.edges:
        source = nodes[edge.source_id].canonical_key
        target = nodes[edge.target_id].canonical_key
        if edge.rel_type == "PRECEDED_BY":
            predecessors[source].append(target)
            successors[target].append(source)
        elif edge.rel_type == "REPLIES_TO" and nodes[edge.target_id].label == "Phantom":
            # A reply points at the absent parent. For the display path, the
            # replying artifact is the successor of the Phantom node.
            successors[target].append(source)

    findings = []
    for node in bundle.nodes:
        if node.label != "Phantom":
            continue
        expected_kind = node.properties.get("expected_kind")
        reason = node.properties.get("reason")
        inferred_epoch = node.properties.get("inferred_epoch")
        predecessor_keys = tuple(sorted(predecessors[node.canonical_key]))
        successor_keys = tuple(sorted(successors[node.canonical_key]))
        findings.append(
            GapFinding(
                phantom_key=node.canonical_key,
                expected_kind=expected_kind if isinstance(expected_kind, str) else "unknown",
                reason=reason if isinstance(reason, str) else "unknown",
                inferred_epoch=(
                    inferred_epoch
                    if type(inferred_epoch) is int
                    else _interpolated_gap_epoch(bundle, predecessor_keys, successor_keys)
                ),
                predecessor_keys=predecessor_keys,
                successor_keys=successor_keys,
            )
        )
    return tuple(sorted(findings, key=lambda finding: finding.phantom_key))


def role_rank(node: NodeRow) -> int:
    value = node.properties.get("role_rank")
    return value if type(value) is int else 0


def _module_owners(
    bundle: CanonicalBundle,
    *,
    min_owner_confidence: int,
) -> dict[str, tuple[tuple[str, int], ...]]:
    nodes = _nodes_by_id(bundle)
    owners: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for edge in bundle.edges:
        if edge.rel_type != "OWNS":
            continue
        confidence = _int_property(edge, "confidence", edge.confidence)
        if confidence <= min_owner_confidence:
            continue
        owner = nodes[edge.source_id].canonical_key
        module = nodes[edge.target_id].canonical_key
        owners[module].append((owner, confidence))
    return {
        module: tuple(sorted(module_owners, key=lambda item: (-item[1], item[0])))
        for module, module_owners in owners.items()
    }


def _bounded_distance(
    graph: CommunicationGraph, source: str, target: str, max_len: int
) -> int | None:
    if source not in graph or target not in graph:
        return None
    if source == target:
        return 0

    queue: deque[tuple[str, int]] = deque([(source, 0)])
    seen = {source}
    while queue:
        node, distance = queue.popleft()
        if distance >= max_len:
            continue
        for neighbor in graph[node]:
            if neighbor in seen:
                continue
            next_distance = distance + 1
            if neighbor == target:
                return next_distance
            seen.add(neighbor)
            queue.append((neighbor, next_distance))
    return None


def _has_path_within(graph: CommunicationGraph, source: str, target: str, max_len: int) -> bool:
    distance = _bounded_distance(graph, source, target, max_len)
    return distance is not None


def _reachable_pair_count(
    graph: CommunicationGraph,
    person_keys: tuple[str, ...],
    max_len: int,
    *,
    use_cache: bool = True,
) -> int:
    ordered = tuple(sorted(person_keys))
    order = {key: index for index, key in enumerate(ordered)}
    total = 0
    for source in ordered:
        reachable = (
            _cached_reachable_within(graph, source, max_len)
            if use_cache
            else _reachable_within(graph, source, max_len)
        )
        for target in reachable:
            if target in order and order[source] < order[target]:
                total += 1
    return total


def _cached_reachable_within(
    graph: CommunicationGraph,
    source: str,
    max_len: int,
) -> frozenset[str]:
    cache_key = (id(graph), source, max_len)
    reachable = _REACHABLE_WITHIN_CACHE.get(cache_key)
    if reachable is None:
        reachable = frozenset(_reachable_within(graph, source, max_len))
        _REACHABLE_WITHIN_CACHE[cache_key] = reachable
    return reachable


def _reachable_within(
    graph: CommunicationGraph,
    source: str,
    max_len: int,
) -> set[str]:
    if source not in graph:
        return set()
    reachable: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(source, 0)])
    seen = {source}
    while queue:
        node, distance = queue.popleft()
        if distance >= max_len:
            continue
        for neighbor in graph[node]:
            if neighbor in seen:
                continue
            seen.add(neighbor)
            reachable.add(neighbor)
            queue.append((neighbor, distance + 1))
    return reachable


def _all_shortest_paths_within(
    graph: CommunicationGraph,
    source: str,
    target: str,
    max_len: int,
) -> tuple[tuple[str, ...], ...]:
    if source not in graph or target not in graph:
        return ()
    if source == target:
        return ((source,),)

    predecessors: dict[str, list[str]] = {source: []}
    distances = {source: 0}
    queue: deque[str] = deque([source])
    target_distance: int | None = None
    while queue:
        node = queue.popleft()
        distance = distances[node]
        if distance >= max_len or (target_distance is not None and distance >= target_distance):
            continue
        for neighbor in sorted(graph[node]):
            next_distance = distance + 1
            if next_distance > max_len:
                continue
            if neighbor not in distances:
                distances[neighbor] = next_distance
                predecessors[neighbor] = [node]
                queue.append(neighbor)
                if neighbor == target:
                    target_distance = next_distance
            elif distances[neighbor] == next_distance:
                predecessors[neighbor].append(node)

    if target not in distances:
        return ()

    def build_paths(node: str) -> tuple[tuple[str, ...], ...]:
        if node == source:
            return ((source,),)
        paths: list[tuple[str, ...]] = []
        for predecessor in predecessors[node]:
            for path in build_paths(predecessor):
                paths.append((*path, node))
        return tuple(paths)

    return build_paths(target)


def _without_node(graph: CommunicationGraph, removed: str) -> CommunicationGraph:
    return {
        node: {neighbor: weight for neighbor, weight in neighbors.items() if neighbor != removed}
        for node, neighbors in graph.items()
        if node != removed
    }


def _bounded_shortest_path_tallies(
    graph: CommunicationGraph,
    person_keys: list[str],
    max_len: int,
) -> tuple[dict[str, float], int]:
    tallies: dict[str, float] = dict.fromkeys(person_keys, 0.0)
    sampled_pairs: set[tuple[str, str]] = set()

    for source in person_keys:
        stack: list[str] = []
        predecessors: dict[str, list[str]] = {key: [] for key in person_keys}
        sigma: dict[str, float] = dict.fromkeys(person_keys, 0.0)
        distance: dict[str, int] = dict.fromkeys(person_keys, -1)
        sigma[source] = 1.0
        distance[source] = 0
        queue: deque[str] = deque([source])

        while queue:
            node = queue.popleft()
            stack.append(node)
            if distance[node] >= max_len:
                continue
            for neighbor in sorted(graph[node]):
                if distance[neighbor] < 0:
                    distance[neighbor] = distance[node] + 1
                    queue.append(neighbor)
                if distance[neighbor] == distance[node] + 1:
                    sigma[neighbor] += sigma[node]
                    predecessors[neighbor].append(node)

        dependency: dict[str, float] = dict.fromkeys(person_keys, 0.0)
        while stack:
            node = stack.pop()
            for predecessor in predecessors[node]:
                if sigma[node] == 0:
                    continue
                dependency[predecessor] += (sigma[predecessor] / sigma[node]) * (
                    1.0 + dependency[node]
                )
            if node != source:
                tallies[node] += dependency[node] / 2
                if 0 < distance[node] <= max_len:
                    sampled_pairs.add(_normalize_pair(source, node))

    return tallies, len(sampled_pairs)


def _normalize_pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def _interpolated_gap_epoch(
    bundle: CanonicalBundle,
    predecessor_keys: tuple[str, ...],
    successor_keys: tuple[str, ...],
) -> int | None:
    nodes = _nodes_by_key(bundle)
    predecessor_epochs = tuple(
        epoch
        for key in predecessor_keys
        if (epoch := nodes[key].properties.get("created_epoch")) is not None and type(epoch) is int
    )
    successor_epochs = tuple(
        epoch
        for key in successor_keys
        if (epoch := nodes[key].properties.get("created_epoch")) is not None and type(epoch) is int
    )
    if not predecessor_epochs or not successor_epochs:
        return None
    return round((max(predecessor_epochs) + min(successor_epochs)) / 2)


__all__ = [
    "TIER_COORDINATED",
    "TIER_NO_PATH",
    "TIER_WEAK",
    "BusFactorImpact",
    "FaultlineFinding",
    "GapFinding",
    "GhostScore",
    "bus_factor_impact",
    "communication_graph",
    "display_name",
    "faultline_tier",
    "faultlines",
    "formal_ranks",
    "gap_findings",
    "ghost_scores",
    "role_rank",
]
