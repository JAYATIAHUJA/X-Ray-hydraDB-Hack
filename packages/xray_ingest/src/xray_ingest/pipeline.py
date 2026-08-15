from __future__ import annotations

from collections.abc import Iterable, Mapping

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
from .sources import code_records, email_records, slack_records, ticket_records


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


def ingest_exports(
    *,
    directory_records: Iterable[CanonicalRecord],
    contracts: SequenceContractSet,
    dataset_id: str,
    canonical_records: Iterable[CanonicalRecord] = (),
    slack_rows: Iterable[Mapping[str, object]] = (),
    email_rows: Iterable[Mapping[str, object]] = (),
    ticket_rows: Iterable[Mapping[str, object]] = (),
    git_rows: Iterable[Mapping[str, object]] = (),
) -> CanonicalBundle:
    """Build one evidence bundle from the supported mixed source exports."""
    records = (
        *tuple(directory_records),
        *tuple(canonical_records),
        *slack_records(slack_rows),
        *email_records(email_rows),
        *ticket_records(ticket_rows),
        *code_records(git_rows),
    )
    return build_bundle(records, contracts, dataset_id)


__all__ = [
    "build_bundle",
    "compose_bundle",
    "ingest_exports",
    "sort_edges",
    "sort_nodes",
]
