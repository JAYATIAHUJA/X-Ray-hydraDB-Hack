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
from .identity import IdentityResolution, resolve_rows, unresolved_directory_records
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
    identity_map: Mapping[str, str] | None = None,
) -> CanonicalBundle:
    """Build one evidence bundle from the supported mixed source exports.

    ``identity_map`` maps source-native ids (email addresses, Slack user ids, …) to
    directory handles. It is applied to every person-id field *before*
    canonicalization; ids that are neither mapped nor already handles get a
    deterministic ``unresolved-…`` handle plus a directory stub and a bundle
    limitation, so real exports never fail on a missing endpoint.
    """
    directory = tuple(directory_records)
    resolution = IdentityResolution()
    known_handles = {
        record.external_id for record in directory if record.kind == "directory_person"
    }
    # Handles that already exist in the directory resolve to themselves.
    effective_map: dict[str, str] = {handle: handle for handle in known_handles}
    effective_map.update(identity_map or {})

    slack = resolve_rows(
        slack_rows, kind="slack", identity_map=effective_map, resolution=resolution
    )
    email = resolve_rows(
        email_rows, kind="email", identity_map=effective_map, resolution=resolution
    )
    tickets = resolve_rows(
        ticket_rows, kind="ticket", identity_map=effective_map, resolution=resolution
    )
    git = resolve_rows(git_rows, kind="git", identity_map=effective_map, resolution=resolution)

    stubs = unresolved_directory_records(
        resolution,
        source=f"{dataset_id}-identity",
        epoch=min((record.occurred_at_epoch for record in directory), default=0),
        known_handles=known_handles,
    )
    records = (
        *directory,
        *stubs,
        *tuple(canonical_records),
        *slack_records(slack),
        *email_records(email),
        *ticket_records(tickets),
        *code_records(git),
    )
    bundle = build_bundle(records, contracts, dataset_id)
    if not resolution.limitations:
        return bundle
    return bundle.model_copy(
        update={"limitations": tuple(sorted({*bundle.limitations, *resolution.limitations}))}
    )


__all__ = [
    "build_bundle",
    "compose_bundle",
    "ingest_exports",
    "sort_edges",
    "sort_nodes",
]
