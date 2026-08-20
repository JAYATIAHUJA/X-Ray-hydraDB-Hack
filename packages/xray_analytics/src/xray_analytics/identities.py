from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from xray_core.models import CanonicalBundle, NodeRow


@dataclass(frozen=True, slots=True)
class IdentityMember:
    person_key: str
    display_name: str
    source_identity: str
    source_type: str


@dataclass(frozen=True, slots=True)
class IdentityCandidate:
    candidate_id: str
    proposed_person_key: str
    proposed_display_name: str
    confidence: int
    signals: tuple[str, ...]
    members: tuple[IdentityMember, ...]
    status: str
    projected_node_reduction: int
    affected_edge_count: int
    duplicate_relationships_removed: int
    limitations: tuple[str, ...]


def identity_candidates(
    bundle: CanonicalBundle,
    decisions: Mapping[str, str] | None = None,
) -> tuple[IdentityCandidate, ...]:
    """Return deterministic, review-only merge candidates emitted by ingestion.

    The function never mutates graph identity.  A reviewer decision can be
    recorded by the API, then applied during a future snapshot rebuild.
    """
    decisions = decisions or {}
    groups: dict[str, list[NodeRow]] = {}
    for node in bundle.nodes:
        candidate_id = node.properties.get("identity_candidate_id")
        if node.label != "Person" or not isinstance(candidate_id, str):
            continue
        groups.setdefault(candidate_id, []).append(node)

    candidates = []
    for candidate_id, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        ordered = sorted(
            members,
            key=lambda node: (
                not bool(node.properties.get("identity_primary", False)),
                node.canonical_key,
            ),
        )
        primary = ordered[0]
        confidence_values = [
            value
            for node in ordered
            if type(value := node.properties.get("identity_confidence")) is int
        ]
        signals = tuple(
            sorted(
                {
                    signal
                    for node in ordered
                    if isinstance((signal := node.properties.get("identity_signal")), str)
                }
            )
        )
        node_ids = {node.id for node in ordered}
        affected_edges = tuple(
            edge
            for edge in bundle.edges
            if edge.source_id in node_ids or edge.target_id in node_ids
        )
        relation_keys = {
            (
                "candidate" if edge.source_id in node_ids else edge.source_id,
                "candidate" if edge.target_id in node_ids else edge.target_id,
                edge.rel_type,
            )
            for edge in affected_edges
        }
        candidates.append(
            IdentityCandidate(
                candidate_id=candidate_id,
                proposed_person_key=primary.canonical_key,
                proposed_display_name=_display_name(primary),
                confidence=min(confidence_values) if confidence_values else 0,
                signals=signals,
                members=tuple(
                    IdentityMember(
                        person_key=node.canonical_key,
                        display_name=_display_name(node),
                        source_identity=str(
                            node.properties.get("source_identity", node.canonical_key)
                        ),
                        source_type=str(node.properties.get("identity_source", "unknown")),
                    )
                    for node in ordered
                ),
                status=decisions.get(candidate_id, "pending"),
                projected_node_reduction=len(ordered) - 1,
                affected_edge_count=len(affected_edges),
                duplicate_relationships_removed=max(0, len(affected_edges) - len(relation_keys)),
                limitations=(
                    "This is a suggested merge, not a confirmed identity fact.",
                    "Accepting queues the decision for a future snapshot rebuild; it does not rewrite source exports.",
                ),
            )
        )
    return tuple(candidates)


def _display_name(node: NodeRow) -> str:
    value = node.properties.get("display_name")
    return value if isinstance(value, str) else node.canonical_key.split(":", 1)[-1]


__all__ = ["IdentityCandidate", "IdentityMember", "identity_candidates"]
