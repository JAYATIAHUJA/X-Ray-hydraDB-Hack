from __future__ import annotations

import hashlib
import json

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


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _empty_sha256() -> str:
    return hashlib.sha256(b"").hexdigest()


def _gap_evidence(
    bundle: CanonicalBundle,
    contract: SequenceContract,
    missing_step: SequenceStep,
) -> EvidenceRecord:
    payload = _canonical_json(
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
        metadata_json=_canonical_json(
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


def detect_gaps(base: CanonicalBundle, contracts: SequenceContractSet) -> GapDerivation:
    node_by_key = {node.canonical_key: node for node in base.nodes}
    phantoms: list[NodeRow] = []
    edges: list[EdgeRow] = []
    evidence_records: list[EvidenceRecord] = []
    limitations = set(contracts.limitations)

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
            phantoms.append(phantom)
            evidence_records.append(gap_evidence)
            sequence_nodes.append(phantom)
            contract_evidence_ids.append(gap_evidence.evidence_id)

        if contract_evidence_ids:
            for later, earlier in zip(sequence_nodes[1:], sequence_nodes, strict=False):
                edges.append(_preceded_by_edge(base, later, earlier, contract, contract_evidence_ids[0]))

    return GapDerivation(
        phantoms=tuple(sorted(phantoms, key=lambda node: (node.id, node.canonical_key))),
        edges=tuple(sorted(edges, key=lambda edge: (edge.id, edge.canonical_key))),
        evidence=tuple(
            sorted(evidence_records, key=lambda evidence: evidence.evidence_id)
        ),
        limitations=tuple(sorted(limitations)),
    )


__all__ = ["detect_gaps"]
