from __future__ import annotations

import hashlib
import json

from xray_core.jsonutil import canonical_json
from xray_core.models import (
    CanonicalBundle,
    EdgeRow,
    EvidenceClass,
    EvidenceRecord,
    GapDerivation,
    NodeRow,
    Scalar,
    SequenceContract,
    SequenceContractSet,
    SequenceStep,
)

from .ids import path_key, stable_edge_id, stable_id


def _empty_sha256() -> str:
    return hashlib.sha256(b"").hexdigest()


def _gap_evidence(
    bundle: CanonicalBundle,
    contract: SequenceContract,
    missing_step: SequenceStep,
) -> EvidenceRecord:
    payload = canonical_json(
        {
            "contract_id": contract.contract_id,
            "dataset_id": bundle.dataset_id,
            "missing_step": missing_step.model_dump(mode="json"),
            "sequence_key": contract.sequence_key,
        }
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return EvidenceRecord(
        evidence_id=f"evidence:{digest}",
        run_id=f"gaps:{bundle.dataset_id}",
        source_type="sequence_contract",
        source_uri=contract.source_uri,
        source_record_id=contract.contract_id,
        observed_epoch=missing_step.earliest_epoch or 0,
        subject_key=missing_step.canonical_key,
        predicate="gap_phantom",
        object_key=contract.sequence_key,
        evidence_class=EvidenceClass.INFERRED,
        confidence=100,
        extraction_method="sequence_contract_gap_detection",
        content_sha256=contract.content_sha256,
        redacted_excerpt="",
        metadata_json=canonical_json(
            {
                "metadata": {
                    "artifact_kind": missing_step.artifact_kind,
                    "contract_id": contract.contract_id,
                    "ordinal": missing_step.ordinal,
                    "required": missing_step.required,
                    "sequence_key": contract.sequence_key,
                }
            }
        ),
    )


def _phantom_node(
    bundle: CanonicalBundle,
    contract: SequenceContract,
    step: SequenceStep,
    evidence: EvidenceRecord,
) -> NodeRow:
    node_id = stable_id(bundle.dataset_id, "Phantom", step.canonical_key)
    properties: dict[str, Scalar] = {
        "contract_ref": contract.contract_id,
        "expected_kind": step.artifact_kind,
        "reason": "required_sequence_step_missing",
    }
    if step.earliest_epoch is not None:
        properties["inferred_epoch"] = step.earliest_epoch
    return NodeRow(
        id=node_id,
        canonical_key=step.canonical_key,
        path_key=path_key("Phantom", node_id),
        label="Phantom",
        evidence_class=EvidenceClass.INFERRED,
        confidence=100,
        properties=properties,
        evidence_ids=(evidence.evidence_id,),
    )


def _preceded_by_edge(
    bundle: CanonicalBundle,
    source: NodeRow,
    target: NodeRow,
    contract: SequenceContract,
    evidence_id: str,
) -> EdgeRow:
    discriminator = f"{contract.contract_id}:{source.canonical_key}:{target.canonical_key}"
    edge_id = stable_edge_id(
        bundle.dataset_id,
        "PRECEDED_BY",
        source.id,
        target.id,
        discriminator,
    )
    return EdgeRow(
        id=edge_id,
        canonical_key=(
            "preceded_by:"
            f"{source.canonical_key.split(':', maxsplit=1)[-1]}:"
            f"{target.canonical_key.split(':', maxsplit=1)[-1]}:"
            f"{contract.contract_id.split(':', maxsplit=1)[-1]}"
        ),
        source_id=source.id,
        target_id=target.id,
        rel_type="PRECEDED_BY",
        evidence_class=EvidenceClass.INFERRED,
        confidence=100,
        properties={
            "contract_id": contract.contract_id,
            "sequence_key": contract.sequence_key,
        },
        evidence_ids=(evidence_id,),
    )


def _thread_parent_evidence(
    bundle: CanonicalBundle,
) -> tuple[tuple[NodeRow, str, EvidenceRecord], ...]:
    nodes = {node.canonical_key: node for node in bundle.nodes}
    missing: list[tuple[NodeRow, str, EvidenceRecord]] = []
    for evidence in bundle.evidence:
        metadata = json.loads(evidence.metadata_json)
        parent_external_id = metadata.get("parent_external_id")
        if not isinstance(parent_external_id, str) or not parent_external_id.strip():
            continue
        child = nodes.get(evidence.subject_key)
        if child is None or child.label != "Artifact":
            continue
        parent_key = (
            parent_external_id
            if parent_external_id.startswith("artifact:")
            else f"artifact:{evidence.source_type}:{parent_external_id}"
        )
        if parent_key not in nodes:
            missing.append((child, parent_key, evidence))
    return tuple(missing)


def _dangling_parent_evidence(
    bundle: CanonicalBundle,
    child: NodeRow,
    parent_key: str,
    source_evidence: EvidenceRecord,
) -> EvidenceRecord:
    payload = canonical_json(
        {
            "child_key": child.canonical_key,
            "dataset_id": bundle.dataset_id,
            "parent_key": parent_key,
            "source_evidence_id": source_evidence.evidence_id,
        }
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return EvidenceRecord(
        evidence_id=f"evidence:{digest}",
        run_id=f"gaps:{bundle.dataset_id}",
        source_type="thread_lineage",
        source_uri=f"derived://{bundle.dataset_id}/dangling-thread-parent/{digest}",
        source_record_id=digest,
        observed_epoch=source_evidence.observed_epoch,
        subject_key=parent_key,
        predicate="gap_phantom",
        object_key=child.canonical_key,
        evidence_class=EvidenceClass.INFERRED,
        confidence=100,
        extraction_method="dangling_thread_parent_detection",
        content_sha256=source_evidence.content_sha256,
        redacted_excerpt="",
        metadata_json=canonical_json(
            {
                "metadata": {
                    "expected_kind": "thread_parent",
                    "reason": "dangling_thread_parent",
                    "source_evidence_id": source_evidence.evidence_id,
                }
            }
        ),
    )


def _dangling_parent_node(
    bundle: CanonicalBundle,
    parent_key: str,
    evidence: EvidenceRecord,
) -> NodeRow:
    node_id = stable_id(bundle.dataset_id, "Phantom", parent_key)
    return NodeRow(
        id=node_id,
        canonical_key=parent_key,
        path_key=path_key("Phantom", node_id),
        label="Phantom",
        evidence_class=EvidenceClass.INFERRED,
        confidence=100,
        properties={
            "expected_kind": "thread_parent",
            "reason": "dangling_thread_parent",
            "inferred_epoch": evidence.observed_epoch,
        },
        evidence_ids=(evidence.evidence_id,),
    )


def _dangling_parent_edge(
    bundle: CanonicalBundle,
    child: NodeRow,
    phantom: NodeRow,
    evidence: EvidenceRecord,
) -> EdgeRow:
    discriminator = f"dangling_thread_parent:{child.canonical_key}:{phantom.canonical_key}"
    edge_id = stable_edge_id(bundle.dataset_id, "REPLIES_TO", child.id, phantom.id, discriminator)
    return EdgeRow(
        id=edge_id,
        canonical_key=(
            f"replies_to:{child.canonical_key.split(':', maxsplit=1)[-1]}:"
            f"{phantom.canonical_key.split(':', maxsplit=1)[-1]}"
        ),
        source_id=child.id,
        target_id=phantom.id,
        rel_type="REPLIES_TO",
        evidence_class=EvidenceClass.INFERRED,
        confidence=100,
        properties={
            "observed_epoch": evidence.observed_epoch,
            "reason": "dangling_thread_parent",
        },
        evidence_ids=(evidence.evidence_id,),
    )


def detect_gaps(base: CanonicalBundle, contracts: SequenceContractSet) -> GapDerivation:
    node_by_key = {node.canonical_key: node for node in base.nodes}
    phantoms: dict[str, NodeRow] = {}
    edges: list[EdgeRow] = []
    evidence_records: list[EvidenceRecord] = []
    limitations = set(contracts.limitations)

    for child, parent_key, source_evidence in _thread_parent_evidence(base):
        gap_evidence = _dangling_parent_evidence(base, child, parent_key, source_evidence)
        phantom = _dangling_parent_node(base, parent_key, gap_evidence)
        phantoms[parent_key] = phantom
        evidence_records.append(gap_evidence)
        edges.append(_dangling_parent_edge(base, child, phantom, gap_evidence))
        limitations.add(
            "A dangling thread parent is structurally absent; absence does not establish deletion."
        )

    for contract in contracts.contracts:
        limitations.update(contract.limitations)
        sequence_nodes: list[NodeRow] = []
        contract_evidence_ids: list[str] = []
        for step in contract.steps:
            existing = node_by_key.get(step.canonical_key)
            if existing is not None:
                sequence_nodes.append(existing)
                continue
            if not step.required:
                continue
            gap_evidence = _gap_evidence(base, contract, step)
            phantom = _phantom_node(base, contract, step, gap_evidence)
            phantoms[step.canonical_key] = phantom
            evidence_records.append(gap_evidence)
            sequence_nodes.append(phantom)
            contract_evidence_ids.append(gap_evidence.evidence_id)

        if contract_evidence_ids:
            for later, earlier in zip(sequence_nodes[1:], sequence_nodes, strict=False):
                edges.append(
                    _preceded_by_edge(base, later, earlier, contract, contract_evidence_ids[0])
                )

    return GapDerivation(
        phantoms=tuple(sorted(phantoms.values(), key=lambda node: (node.id, node.canonical_key))),
        edges=tuple(sorted(edges, key=lambda edge: (edge.id, edge.canonical_key))),
        evidence=tuple(sorted(evidence_records, key=lambda evidence: evidence.evidence_id)),
        limitations=tuple(sorted(limitations)),
    )


__all__ = ["detect_gaps"]
