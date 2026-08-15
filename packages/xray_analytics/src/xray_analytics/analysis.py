from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from itertools import combinations

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


def _display_name(node: NodeRow) -> str:
    value = node.properties.get("display_name") or node.properties.get("handle")
    return value if isinstance(value, str) else node.canonical_key


def _int_property(edge: EdgeRow, key: str, default: int) -> int:
    value = edge.properties.get(key)
    return value if type(value) is int else default


type CommunicationGraph = dict[str, dict[str, int]]


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

    graph = communication_graph(bundle)
    people = _person_nodes(bundle)
    person_keys = [person.canonical_key for person in people]
    tallies: dict[str, float] = dict.fromkeys(person_keys, 0.0)
    sampled_pairs = 0

    for source, target in combinations(person_keys, 2):
        paths = _all_shortest_paths_within(graph, source, target, max_len)
        if not paths:
            continue
        sampled_pairs += 1
        path_credit = 1.0 / len(paths)
        for path in paths:
            for intermediate in path[1:-1]:
                tallies[intermediate] += path_credit

    denominator = float(sampled_pairs or 1)
    centrality = {key: tallies[key] / denominator for key in person_keys}
    structural_order = sorted(person_keys, key=lambda key: (-centrality[key], key))
    structural_rank = {key: index for index, key in enumerate(structural_order, start=1)}
    formal_order = sorted(
        people,
        key=lambda node: (-_role_rank(node), node.canonical_key),
    )
    formal_rank = {node.canonical_key: index for index, node in enumerate(formal_order, start=1)}

    scores = [
        GhostScore(
            person_key=node.canonical_key,
            display_name=_display_name(node),
            role_rank=_role_rank(node),
            structural_rank=structural_rank[node.canonical_key],
            formal_rank=formal_rank[node.canonical_key],
            rank_gap=formal_rank[node.canonical_key] - structural_rank[node.canonical_key],
            sampled_centrality=centrality[node.canonical_key],
            communication_degree=len(graph[node.canonical_key]),
        )
        for node in people
    ]
    return tuple(sorted(scores, key=lambda score: (-score.sampled_centrality, score.person_key)))


def bus_factor_impact(
    bundle: CanonicalBundle, person_key: str, *, max_len: int = 4
) -> BusFactorImpact:
    if max_len <= 0:
        raise ValueError("max_len must be positive")

    graph = communication_graph(bundle)
    if person_key not in graph:
        raise ValueError(f"unknown person_key {person_key!r}")

    before = 0
    lost = 0
    remaining_people = tuple(node for node in graph if node != person_key)
    reduced_graph = _without_node(graph, person_key)
    for source, target in combinations(remaining_people, 2):
        if _has_path_within(graph, source, target, max_len):
            before += 1
            if not _has_path_within(reduced_graph, source, target, max_len):
                lost += 1
    return BusFactorImpact(
        person_key=person_key,
        reachable_pairs_before=before,
        pairs_lost_without_person=lost,
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
                if distance is None:
                    tier = "no_path"
                    risk = 1.0
                elif distance >= 3:
                    tier = "weak_coordination"
                    risk = 0.5
                else:
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


def _role_rank(node: NodeRow) -> int:
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
        for neighbor in sorted(graph[node]):
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


def _all_shortest_paths_within(
    graph: CommunicationGraph,
    source: str,
    target: str,
    max_len: int,
) -> tuple[tuple[str, ...], ...]:
    distance = _bounded_distance(graph, source, target, max_len)
    if distance is None:
        return ()

    paths: list[tuple[str, ...]] = []
    queue: deque[tuple[str, ...]] = deque([(source,)])
    while queue:
        path = queue.popleft()
        if len(path) - 1 == distance:
            if path[-1] == target:
                paths.append(path)
            continue
        for neighbor in sorted(graph[path[-1]]):
            if neighbor in path:
                continue
            queue.append((*path, neighbor))
    return tuple(paths)


def _without_node(graph: CommunicationGraph, removed: str) -> CommunicationGraph:
    return {
        node: {neighbor: weight for neighbor, weight in neighbors.items() if neighbor != removed}
        for node, neighbors in graph.items()
        if node != removed
    }


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
    "BusFactorImpact",
    "FaultlineFinding",
    "GapFinding",
    "GhostScore",
    "bus_factor_impact",
    "communication_graph",
    "faultlines",
    "gap_findings",
    "ghost_scores",
]
