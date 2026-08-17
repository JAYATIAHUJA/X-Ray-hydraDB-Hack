from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

from xray_core.jsonutil import canonical_json
from xray_core.models import (
    CanonicalBundle,
    CanonicalRecord,
    EdgeRow,
    EvidenceClass,
    EvidenceRecord,
    NodeRow,
    Scalar,
)

from .ids import IdFactory, IdRegistry, path_key, stable_edge_id, stable_id

NodeLabel = Literal["Person", "Team", "Artifact", "Module", "Phantom"]
RelationType = Literal[
    "REPORTS_TO",
    "AUTHORED",
    "REPLIES_TO",
    "MENTIONS",
    "COMMUNICATES",
    "ABOUT",
    "OWNS",
    "DEPENDS_ON",
    "PRECEDED_BY",
]


class CanonicalizationError(ValueError):
    """Raised when source facts cannot be normalized without ambiguity."""


@dataclass(frozen=True, slots=True)
class RecordEnvelope:
    record: CanonicalRecord
    payload_json: str
    evidence: EvidenceRecord


def _record_payload(record: CanonicalRecord) -> str:
    return canonical_json(record.model_dump(mode="json"))


def _record_evidence(
    record: CanonicalRecord,
    dataset_id: str,
    payload_json: str,
) -> EvidenceRecord:
    evidence_digest = hashlib.sha256(f"{dataset_id}|evidence|{payload_json}".encode()).hexdigest()
    fallback_key = f"record:{record.source}:{record.external_id}"
    subject_key = record.subjects[0] if record.subjects else fallback_key
    object_key = record.subjects[1] if len(record.subjects) > 1 else subject_key
    metadata_json = canonical_json(
        {
            "author_external_id": record.author_external_id,
            "metadata": record.metadata,
            "parent_external_id": record.parent_external_id,
            "subjects": record.subjects,
        }
    )
    configured_class = record.metadata.get("evidence_class")
    if configured_class is not None:
        if not isinstance(configured_class, str):
            raise CanonicalizationError("evidence_class metadata must be a string")
        try:
            evidence_class = EvidenceClass(configured_class)
        except ValueError as error:
            raise CanonicalizationError(
                f"Unsupported evidence_class metadata {configured_class!r}"
            ) from error
    elif record.kind in {"cochange", "inferred_coupling"} or (
        record.metadata.get("relationship_class") == "inferred_coupling"
    ):
        evidence_class = EvidenceClass.INFERRED
    else:
        evidence_class = EvidenceClass.OBSERVED
    return EvidenceRecord(
        evidence_id=f"evidence:{evidence_digest}",
        run_id=f"canonicalize:{dataset_id}",
        source_type=record.source,
        source_uri=(
            f"record://{quote(record.source, safe='')}/{quote(record.external_id, safe='')}"
        ),
        source_record_id=record.external_id,
        observed_epoch=record.occurred_at_epoch,
        subject_key=subject_key,
        predicate=record.kind,
        object_key=object_key,
        evidence_class=evidence_class,
        confidence=100,
        extraction_method="canonical_record",
        content_sha256=record.content_sha256,
        redacted_excerpt="" if record.content is None else "[content redacted]",
        metadata_json=metadata_json,
    )


def _prepare_records(
    records: Iterable[CanonicalRecord],
    dataset_id: str,
) -> tuple[RecordEnvelope, ...]:
    by_source_identity: dict[tuple[str, str], tuple[str, CanonicalRecord]] = {}
    for record in records:
        if not isinstance(record, CanonicalRecord):
            raise TypeError("canonicalize expects CanonicalRecord instances")
        payload_json = _record_payload(record)
        source_identity = (record.source, record.external_id)
        previous = by_source_identity.get(source_identity)
        if previous is not None and previous[0] != payload_json:
            raise CanonicalizationError(
                f"Conflicting source record for {record.source!r}/{record.external_id!r}"
            )
        by_source_identity[source_identity] = (payload_json, record)

    envelopes = [
        RecordEnvelope(
            record=record,
            payload_json=payload_json,
            evidence=_record_evidence(record, dataset_id, payload_json),
        )
        for payload_json, record in by_source_identity.values()
    ]
    return tuple(
        sorted(
            envelopes,
            key=lambda envelope: (
                envelope.record.source,
                envelope.record.external_id,
                envelope.record.kind,
                envelope.payload_json,
            ),
        )
    )


def _node_label(record: CanonicalRecord) -> NodeLabel | None:
    return {
        "directory_person": "Person",
        "directory_team": "Team",
        "team": "Team",
        "artifact": "Artifact",
        "module": "Module",
    }.get(record.kind)  # type: ignore[return-value]


def _node_canonical_key(record: CanonicalRecord, label: NodeLabel) -> str:
    configured_key = record.metadata.get("canonical_key")
    if isinstance(configured_key, str):
        return configured_key

    prefix = {
        "Person": "person:",
        "Team": "team:",
        "Artifact": "artifact:",
        "Module": "module:",
        "Phantom": "artifact:",
    }[label]
    matching_subjects = [subject for subject in record.subjects if subject.startswith(prefix)]
    if matching_subjects:
        return matching_subjects[0]
    return f"{prefix}{record.external_id}"


def _metadata_scalar(record: CanonicalRecord, key: str) -> Scalar | None:
    return record.metadata.get(key)


def _node_properties(record: CanonicalRecord, label: NodeLabel) -> dict[str, Scalar]:
    properties: dict[str, Scalar]
    if label == "Person":
        properties = {"handle": record.external_id}
        field_map = {
            "display_name": "display_name",
            "role_rank": "role_rank",
            "team_key": "team_id",
            # Present only on identity stubs synthesized for unmapped source ids.
            "identity_status": "identity_status",
            "source_identity": "source_identity",
        }
    elif label == "Team":
        properties = {"name": record.external_id}
        field_map = {"parent_team_id": "parent_team_id"}
    elif label == "Artifact":
        properties = {
            "created_epoch": record.occurred_at_epoch,
            "ext_ref": record.external_id,
            "source_type": record.source,
        }
        field_map = {
            "artifact_kind": "kind",
            "sequence_ordinal": "thread_seq",
        }
    elif label == "Module":
        properties = {"name": record.external_id}
        field_map = {
            "criticality": "criticality",
            "language": "language",
            "module_name": "name",
            "repo": "repo",
        }
    else:
        properties = {}
        field_map = {}

    for source_key, target_key in field_map.items():
        value = _metadata_scalar(record, source_key)
        if value is not None:
            properties[target_key] = value
    return dict(sorted(properties.items()))


def _key_suffix(canonical_key: str) -> str:
    return canonical_key.split(":", maxsplit=1)[-1]


def _relationship_properties(record: CanonicalRecord) -> dict[str, Scalar]:
    return {"observed_epoch": record.occurred_at_epoch}


class BundleBuilder:
    def __init__(self, dataset_id: str, id_factory: IdFactory) -> None:
        self.dataset_id = dataset_id
        self.registry = IdRegistry(id_factory=id_factory)
        self.id_factory = id_factory
        self.nodes: dict[str, NodeRow] = {}
        self.edges: dict[str, EdgeRow] = {}

    def add_node(self, envelope: RecordEnvelope) -> None:
        label = _node_label(envelope.record)
        if label is None:
            return
        canonical_key = _node_canonical_key(envelope.record, label)
        node_id = self.registry.register(self.dataset_id, label, canonical_key)
        node = NodeRow(
            id=node_id,
            canonical_key=canonical_key,
            path_key=path_key(label, node_id),
            label=label,
            evidence_class=envelope.evidence.evidence_class,
            confidence=100,
            properties=_node_properties(envelope.record, label),
            evidence_ids=(envelope.evidence.evidence_id,),
        )
        existing = self.nodes.get(canonical_key)
        if existing is not None:
            if existing.model_copy(update={"evidence_ids": ()}) != node.model_copy(
                update={"evidence_ids": ()}
            ):
                raise CanonicalizationError(f"Conflicting node identity {canonical_key!r}")
            node = existing.model_copy(
                update={"evidence_ids": tuple(sorted({*existing.evidence_ids, *node.evidence_ids}))}
            )
        self.nodes[canonical_key] = node

    def require_node(self, canonical_key: str) -> NodeRow:
        node = self.nodes.get(canonical_key)
        if node is None:
            raise CanonicalizationError(f"Relationship references missing node {canonical_key!r}")
        return node

    def add_edge(
        self,
        *,
        canonical_key: str,
        source_key: str,
        target_key: str,
        rel_type: RelationType,
        semantic_discriminator: str,
        properties: dict[str, Scalar],
        evidence_id: str,
        evidence_class: EvidenceClass,
    ) -> None:
        source = self.require_node(source_key)
        target = self.require_node(target_key)
        edge_id = stable_edge_id(
            self.dataset_id,
            rel_type,
            source.id,
            target.id,
            semantic_discriminator,
            id_factory=self.id_factory,
        )
        self.registry.register(
            self.dataset_id,
            rel_type,
            canonical_key,
            identity_id=edge_id,
        )
        edge = EdgeRow(
            id=edge_id,
            canonical_key=canonical_key,
            source_id=source.id,
            target_id=target.id,
            rel_type=rel_type,
            evidence_class=evidence_class,
            confidence=100,
            properties=properties,
            evidence_ids=(evidence_id,),
        )
        existing = self.edges.get(canonical_key)
        if existing is not None:
            if existing.model_copy(update={"evidence_ids": ()}) != edge.model_copy(
                update={"evidence_ids": ()}
            ):
                raise CanonicalizationError(f"Conflicting edge identity {canonical_key!r}")
            edge = existing.model_copy(
                update={"evidence_ids": tuple(sorted({*existing.evidence_ids, *edge.evidence_ids}))}
            )
        self.edges[canonical_key] = edge


def _add_reporting_edge(builder: BundleBuilder, envelope: RecordEnvelope) -> None:
    manager_external_id = envelope.record.metadata.get("manager_external_id")
    if manager_external_id is None:
        return
    if not isinstance(manager_external_id, str) or not manager_external_id.strip():
        raise CanonicalizationError("manager_external_id must be a non-empty string")

    source_key = _node_canonical_key(envelope.record, "Person")
    target_key = f"person:{manager_external_id}"
    builder.add_edge(
        canonical_key=f"reporting:{_key_suffix(source_key)}:{_key_suffix(target_key)}",
        source_key=source_key,
        target_key=target_key,
        rel_type="REPORTS_TO",
        semantic_discriminator="reporting_line",
        properties=_relationship_properties(envelope.record),
        evidence_id=envelope.evidence.evidence_id,
        evidence_class=envelope.evidence.evidence_class,
    )


def _add_artifact_authorship_edge(builder: BundleBuilder, envelope: RecordEnvelope) -> None:
    record = envelope.record
    if record.author_external_id is None:
        return
    artifact_key = _node_canonical_key(record, "Artifact")
    source_key = f"person:{record.author_external_id}"
    target_key = artifact_key
    builder.add_edge(
        canonical_key=f"authorship:{_key_suffix(source_key)}:{_key_suffix(target_key)}",
        source_key=source_key,
        target_key=target_key,
        rel_type="AUTHORED",
        semantic_discriminator="authored",
        properties=_relationship_properties(record),
        evidence_id=envelope.evidence.evidence_id,
        evidence_class=envelope.evidence.evidence_class,
    )


def _add_about_edge(builder: BundleBuilder, envelope: RecordEnvelope) -> None:
    record = envelope.record
    module_subjects = sorted(
        {subject for subject in record.subjects if subject.startswith("module:")}
    )
    if not module_subjects:
        return
    source_key = _node_canonical_key(record, "Artifact")
    for target_key in module_subjects:
        builder.add_edge(
            canonical_key=f"about:{_key_suffix(source_key)}:{_key_suffix(target_key)}",
            source_key=source_key,
            target_key=target_key,
            rel_type="ABOUT",
            semantic_discriminator="about",
            properties=_relationship_properties(record),
            evidence_id=envelope.evidence.evidence_id,
            evidence_class=envelope.evidence.evidence_class,
        )


def _reply_target_key(record: CanonicalRecord) -> str | None:
    parent_external_id = record.parent_external_id
    if parent_external_id is None:
        return None
    if parent_external_id.startswith("artifact:"):
        return parent_external_id
    return f"artifact:{record.source}:{parent_external_id}"


def _add_reply_edge(builder: BundleBuilder, envelope: RecordEnvelope) -> None:
    record = envelope.record
    source_key = _node_canonical_key(record, "Artifact")
    target_key = _reply_target_key(record)
    if target_key is None or target_key not in builder.nodes:
        return
    builder.add_edge(
        canonical_key=f"replies_to:{_key_suffix(source_key)}:{_key_suffix(target_key)}",
        source_key=source_key,
        target_key=target_key,
        rel_type="REPLIES_TO",
        semantic_discriminator="thread_parent",
        properties=_relationship_properties(record),
        evidence_id=envelope.evidence.evidence_id,
        evidence_class=envelope.evidence.evidence_class,
    )


def _add_observed_edges(builder: BundleBuilder, envelopes: tuple[RecordEnvelope, ...]) -> None:
    for envelope in envelopes:
        record = envelope.record
        if record.kind == "directory_person":
            _add_reporting_edge(builder, envelope)
        elif record.kind == "artifact":
            _add_artifact_authorship_edge(builder, envelope)
            _add_about_edge(builder, envelope)
            _add_reply_edge(builder, envelope)
        # Communication, ownership, dependency, co-change, and lineage remain evidence facts.
        # Task 3 derives their aggregate or inferred topology without fabricating edges here.


def canonicalize(
    records: Iterable[CanonicalRecord],
    dataset_id: str,
    *,
    id_factory: IdFactory = stable_id,
) -> CanonicalBundle:
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("dataset_id must be a non-empty string")

    envelopes = _prepare_records(records, dataset_id)
    builder = BundleBuilder(dataset_id, id_factory)
    for envelope in envelopes:
        builder.add_node(envelope)
    _add_observed_edges(builder, envelopes)

    return CanonicalBundle(
        dataset_id=dataset_id,
        nodes=tuple(sorted(builder.nodes.values(), key=lambda node: (node.id, node.canonical_key))),
        edges=tuple(sorted(builder.edges.values(), key=lambda edge: (edge.id, edge.canonical_key))),
        evidence=tuple(
            sorted(
                (envelope.evidence for envelope in envelopes),
                key=lambda evidence: evidence.evidence_id,
            )
        ),
    )


__all__ = ["CanonicalizationError", "canonicalize"]
