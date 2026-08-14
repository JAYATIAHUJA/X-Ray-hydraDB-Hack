from __future__ import annotations

from collections.abc import Iterable

from xray_core.models import (
    CanonicalBundle,
    CanonicalRecord,
    EdgeRow,
    GapDerivation,
    NodeRow,
    SequenceContractSet,
)

from .canonicalize import canonicalize
from .derive import derive_edges
from .gaps import detect_gaps


def sort_nodes(nodes: Iterable[NodeRow]) -> tuple[NodeRow, ...]:
    return tuple(sorted(nodes, key=lambda node: (node.id, node.canonical_key)))


def sort_edges(edges: Iterable[EdgeRow]) -> tuple[EdgeRow, ...]:
    return tuple(sorted(edges, key=lambda edge: (edge.id, edge.canonical_key)))


def compose_bundle(
    base: CanonicalBundle,
    derived_edges: tuple[EdgeRow, ...],
    gaps: GapDerivation,
) -> CanonicalBundle:
    return CanonicalBundle(
        dataset_id=base.dataset_id,
        nodes=sort_nodes((*base.nodes, *gaps.phantoms)),
        edges=sort_edges((*base.edges, *derived_edges, *gaps.edges)),
        evidence=tuple(
            sorted(
                (*base.evidence, *gaps.evidence),
                key=lambda evidence: evidence.evidence_id,
            )
        ),
        limitations=tuple(sorted({*base.limitations, *gaps.limitations})),
    )


def build_bundle(
    records: Iterable[CanonicalRecord],
    contracts: SequenceContractSet,
    dataset_id: str,
) -> CanonicalBundle:
    base = canonicalize(records, dataset_id)
    return compose_bundle(base, derive_edges(base), detect_gaps(base, contracts))


__all__ = ["build_bundle", "compose_bundle", "sort_edges", "sort_nodes"]
