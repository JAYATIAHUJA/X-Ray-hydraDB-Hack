from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from xray_core.models import CanonicalBundle, EdgeRow, EvidenceClass, EvidenceRecord, Scalar

from .ids import stable_edge_id


class DerivationError(ValueError):
    """Raised when deterministic graph derivation cannot resolve source evidence."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _evidence_metadata(record: EvidenceRecord) -> dict[str, object]:
    parsed = json.loads(record.metadata_json)
    metadata = parsed.get("metadata")
    if not isinstance(metadata, dict):
        raise DerivationError(f"{record.evidence_id} metadata_json lacks a metadata object")
    return metadata


def _int_metadata(metadata: dict[str, object], key: str, evidence_id: str) -> int:
    value = metadata.get(key)
    if type(value) is not int:
        raise DerivationError(f"{evidence_id} metadata {key!r} must be an integer")
    return value


def _str_metadata(metadata: dict[str, object], key: str, evidence_id: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DerivationError(f"{evidence_id} metadata {key!r} must be a non-empty string")
    return value


def _edge_key(source_key: str, target_key: str, rel_type: str, discriminator: str) -> str:
    left = source_key.split(":", maxsplit=1)[-1]
    right = target_key.split(":", maxsplit=1)[-1]
    return f"{rel_type.lower()}:{left}:{right}:{discriminator}"


def _derived_evidence(
    *,
    bundle: CanonicalBundle,
    predicate: str,
    subject_key: str,
    object_key: str,
    source_evidence_ids: tuple[str, ...],
    metadata: dict[str, Scalar],
    observed_epoch: int,
) -> EvidenceRecord:
    payload = _canonical_json(
        {
            "dataset_id": bundle.dataset_id,
            "metadata": metadata,
            "object_key": object_key,
            "predicate": predicate,
            "source_evidence_ids": source_evidence_ids,
            "subject_key": subject_key,
        }
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return EvidenceRecord(
        evidence_id=f"evidence:{digest}",
        run_id=f"derive:{bundle.dataset_id}",
        source_type="derived",
        source_uri=f"derived://{bundle.dataset_id}/{predicate}/{digest}",
        source_record_id=digest,
        observed_epoch=observed_epoch,
        subject_key=subject_key,
        predicate=predicate,
        object_key=object_key,
        evidence_class=EvidenceClass.INFERRED,
        confidence=100,
        extraction_method="deterministic_derivation",
        content_sha256=hashlib.sha256(b"").hexdigest(),
        redacted_excerpt="",
        metadata_json=_canonical_json({"metadata": metadata}),
    )


def _add_edge(
    bundle: CanonicalBundle,
    *,
    source_key: str,
    target_key: str,
    rel_type: str,
    discriminator: str,
    properties: dict[str, Scalar],
    evidence_ids: tuple[str, ...],
    evidence_class: EvidenceClass,
) -> EdgeRow:
    nodes = {node.canonical_key: node for node in bundle.nodes}
    source = nodes.get(source_key)
    target = nodes.get(target_key)
    if source is None or target is None:
        raise DerivationError(f"{rel_type} references a missing endpoint")
    edge_id = stable_edge_id(bundle.dataset_id, rel_type, source.id, target.id, discriminator)
    return EdgeRow(
        id=edge_id,
        canonical_key=_edge_key(source_key, target_key, rel_type, discriminator),
        source_id=source.id,
        target_id=target.id,
        rel_type=rel_type,  # type: ignore[arg-type]
        evidence_class=evidence_class,
        confidence=100,
        properties=properties,
        evidence_ids=evidence_ids,
    )


@dataclass(frozen=True, slots=True)
class CommunicationAggregate:
    source_key: str
    target_key: str
    first_epoch: int
    last_epoch: int
    mention_weight: int = 0
    reply_weight: int = 0
    evidence_ids: tuple[str, ...] = ()

    def add(
        self,
        kind: str,
        count: int,
        first_epoch: int,
        last_epoch: int,
        evidence_id: str,
    ) -> CommunicationAggregate:
        return CommunicationAggregate(
            source_key=self.source_key,
            target_key=self.target_key,
            first_epoch=min(self.first_epoch, first_epoch),
            last_epoch=max(self.last_epoch, last_epoch),
            mention_weight=self.mention_weight + (count if kind == "mention" else 0),
            reply_weight=self.reply_weight + (count if kind == "reply" else 0),
            evidence_ids=tuple(sorted((*self.evidence_ids, evidence_id))),
        )


def _communication_edges(bundle: CanonicalBundle) -> tuple[EdgeRow, ...]:
    aggregates: dict[tuple[str, str], CommunicationAggregate] = {}
    for evidence in bundle.evidence:
        if evidence.predicate != "communication_aggregate":
            continue
        metadata = _evidence_metadata(evidence)
        source_key = f"person:{_str_metadata(metadata, 'sender_external_id', evidence.evidence_id)}"
        target_key = f"person:{_str_metadata(metadata, 'recipient_external_id', evidence.evidence_id)}"
        kind = _str_metadata(metadata, "interaction_kind", evidence.evidence_id)
        if kind not in {"mention", "reply"}:
            raise DerivationError(f"{evidence.evidence_id} has unsupported interaction_kind {kind!r}")
        count = _int_metadata(metadata, "interaction_count", evidence.evidence_id)
        first_epoch = _int_metadata(metadata, "first_epoch", evidence.evidence_id)
        last_epoch = _int_metadata(metadata, "last_epoch", evidence.evidence_id)
        key = (source_key, target_key)
        current = aggregates.get(key) or CommunicationAggregate(source_key, target_key, first_epoch, last_epoch)
        aggregates[key] = current.add(kind, count, first_epoch, last_epoch, evidence.evidence_id)

    edges = []
    for aggregate in aggregates.values():
        total = aggregate.mention_weight + aggregate.reply_weight
        edges.append(
            _add_edge(
                bundle,
                source_key=aggregate.source_key,
                target_key=aggregate.target_key,
                rel_type="COMMUNICATES",
                discriminator="aggregate",
                properties={
                    "first_epoch": aggregate.first_epoch,
                    "last_epoch": aggregate.last_epoch,
                    "mention_weight": aggregate.mention_weight,
                    "reply_weight": aggregate.reply_weight,
                    "weight": total,
                },
                evidence_ids=aggregate.evidence_ids,
                evidence_class=EvidenceClass.INFERRED,
            )
        )
    return tuple(edges)


def _ownership_edges(bundle: CanonicalBundle) -> tuple[EdgeRow, ...]:
    edges = []
    for evidence in bundle.evidence:
        if evidence.predicate != "authorship_aggregate":
            continue
        metadata = _evidence_metadata(evidence)
        attributed = _int_metadata(metadata, "attributed_count", evidence.evidence_id)
        total = _int_metadata(metadata, "total_attributed_count", evidence.evidence_id)
        if total <= 0 or attributed < 0 or attributed > total:
            raise DerivationError(f"{evidence.evidence_id} has invalid authorship counts")
        confidence = round((attributed / total) * 100)
        edges.append(
            _add_edge(
                bundle,
                source_key=evidence.subject_key,
                target_key=evidence.object_key,
                rel_type="OWNS",
                discriminator="authorship_density",
                properties={
                    "attributed_count": attributed,
                    "confidence": confidence,
                    "total_attributed_count": total,
                },
                evidence_ids=(evidence.evidence_id,),
                evidence_class=EvidenceClass.INFERRED,
            )
        )
    return tuple(edges)


def _dependency_edges(bundle: CanonicalBundle) -> tuple[EdgeRow, ...]:
    allowed_kinds = {"import", "manifest", "runtime_call", "explicit_reference"}
    edges = []
    for evidence in bundle.evidence:
        if evidence.predicate != "dependency":
            continue
        metadata = _evidence_metadata(evidence)
        dependency_kind = _str_metadata(metadata, "dependency_kind", evidence.evidence_id)
        if dependency_kind not in allowed_kinds:
            raise DerivationError(f"{evidence.evidence_id} has unsupported dependency_kind")
        weight = _int_metadata(metadata, "weight", evidence.evidence_id)
        edges.append(
            _add_edge(
                bundle,
                source_key=evidence.subject_key,
                target_key=evidence.object_key,
                rel_type="DEPENDS_ON",
                discriminator=dependency_kind,
                properties={"dependency_kind": dependency_kind, "weight": weight},
                evidence_ids=(evidence.evidence_id,),
                evidence_class=evidence.evidence_class,
            )
        )
    return tuple(edges)


def derive_edges(base: CanonicalBundle) -> tuple[EdgeRow, ...]:
    edges = (*_communication_edges(base), *_ownership_edges(base), *_dependency_edges(base))
    return tuple(sorted(edges, key=lambda edge: (edge.id, edge.canonical_key)))


__all__ = ["DerivationError", "derive_edges"]
