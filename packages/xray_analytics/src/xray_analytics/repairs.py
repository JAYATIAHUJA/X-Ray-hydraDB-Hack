"""Coordination Repair Ledger — propose non-personnel repairs and prove closure."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from xray_core.jsonutil import canonical_json
from xray_core.models import (
    CanonicalBundle,
    EdgeRow,
    EvidenceClass,
    EvidenceRecord,
    NodeRow,
)
from xray_ingest.ids import path_key, stable_edge_id

from .analysis import FaultlineFinding, GapFinding, faultlines, gap_findings

RepairKind = Literal[
    "record_missing_approval",
    "establish_owner_bridge",
    "add_backup_owner",
    "publish_codeowners",
]
RepairVerdict = Literal["SUPPORTED", "UNSUPPORTED", "UNKNOWN"]
RepairStatus = Literal["proposed", "approved", "rejected", "closed", "open"]


@dataclass(frozen=True, slots=True)
class RepairProposal:
    repair_id: str
    finding_kind: Literal["gap", "faultline"]
    finding_key: str
    title: str
    repair_kind: RepairKind
    summary: str
    verdict: RepairVerdict
    evidence_ids: tuple[str, ...]
    limitations: tuple[str, ...]
    status: RepairStatus = "proposed"
    closed: bool = False


@dataclass(frozen=True, slots=True)
class ApprovedRepair:
    repair_id: str
    repair_kind: RepairKind
    finding_kind: Literal["gap", "faultline"]
    finding_key: str
    payload: Mapping[str, str]


def propose_repairs(bundle: CanonicalBundle) -> tuple[RepairProposal, ...]:
    """Derive non-personnel repair proposals from open gaps and faultlines."""
    proposals: list[RepairProposal] = []
    for gap in gap_findings(bundle):
        proposals.append(_gap_repair(bundle, gap))
    for finding in faultlines(bundle)[:5]:
        proposals.append(_faultline_repair(bundle, finding))
    return tuple(proposals)


def apply_approved_repairs(
    bundle: CanonicalBundle,
    approved: Sequence[ApprovedRepair],
) -> CanonicalBundle:
    """Return a bundle with approved repair overlays applied (immutable)."""
    current = bundle
    for repair in approved:
        if repair.repair_kind == "record_missing_approval":
            current = _apply_gap_closure(current, repair.finding_key)
        elif repair.repair_kind in {
            "establish_owner_bridge",
            "add_backup_owner",
            "publish_codeowners",
        }:
            source = repair.payload.get("source_owner_key", "")
            target = repair.payload.get("target_owner_key", "")
            module = repair.payload.get("module_key", "")
            if repair.repair_kind == "establish_owner_bridge" and source and target:
                current = _apply_owner_bridge(current, source, target, repair.repair_id)
            elif repair.repair_kind == "add_backup_owner" and module and target:
                current = _apply_backup_owner(current, module, target, repair.repair_id)
            elif repair.repair_kind == "publish_codeowners" and module and source:
                current = _apply_backup_owner(current, module, source, repair.repair_id)
    return current


def verify_repair(
    bundle: CanonicalBundle,
    proposal: RepairProposal,
) -> tuple[bool, str]:
    """Re-run the originating lens; closed when the finding is gone."""
    if proposal.finding_kind == "gap":
        open_keys = {item.phantom_key for item in gap_findings(bundle)}
        closed = proposal.finding_key not in open_keys
        return closed, "gap_absent" if closed else "gap_still_open"
    open_keys = {_faultline_key(item) for item in faultlines(bundle)}
    closed = proposal.finding_key not in open_keys
    return closed, "faultline_absent" if closed else "faultline_still_open"


def with_status(
    proposals: Sequence[RepairProposal],
    *,
    statuses: Mapping[str, RepairStatus],
    closed: Mapping[str, bool] | None = None,
) -> tuple[RepairProposal, ...]:
    closed = closed or {}
    return tuple(
        RepairProposal(
            repair_id=item.repair_id,
            finding_kind=item.finding_kind,
            finding_key=item.finding_key,
            title=item.title,
            repair_kind=item.repair_kind,
            summary=item.summary,
            verdict=item.verdict,
            evidence_ids=item.evidence_ids,
            limitations=item.limitations,
            status=statuses.get(item.repair_id, item.status),
            closed=closed.get(item.repair_id, item.closed),
        )
        for item in proposals
    )


def _gap_repair(bundle: CanonicalBundle, gap: GapFinding) -> RepairProposal:
    evidence_ids = tuple(
        node.evidence_ids[0]
        for node in bundle.nodes
        if node.canonical_key == gap.phantom_key and node.evidence_ids
    )
    return RepairProposal(
        repair_id=f"repair:gap:{gap.phantom_key}",
        finding_kind="gap",
        finding_key=gap.phantom_key,
        title=f"Record missing {gap.expected_kind} evidence",
        repair_kind="record_missing_approval",
        summary=(
            f"Materialize {gap.phantom_key} as an observed approval artifact so the "
            "required sequence is complete and Phantom gap findings clear."
        ),
        verdict="SUPPORTED" if gap.predecessor_keys and gap.successor_keys else "UNKNOWN",
        evidence_ids=evidence_ids,
        limitations=(
            "Approving records an obligation overlay on this snapshot; it does not rewrite source exports.",
            "Absence elsewhere may still be export filtering rather than a true missing approval.",
        ),
    )


def _faultline_repair(bundle: CanonicalBundle, finding: FaultlineFinding) -> RepairProposal:
    finding_key = _faultline_key(finding)
    evidence_ids = tuple(
        edge.evidence_ids[0]
        for edge in bundle.edges
        if edge.rel_type == "DEPENDS_ON" and edge.evidence_ids
    )[:3]
    if finding.communication_distance is None:
        kind: RepairKind = "establish_owner_bridge"
        title = "Establish owner coordination path"
        summary = (
            f"Add an observed communication bridge between {finding.source_owner_key} and "
            f"{finding.target_owner_key} for the {finding.source_module_key} → "
            f"{finding.target_module_key} dependency."
        )
        verdict: RepairVerdict = "SUPPORTED"
    elif finding.tier == "weak_coordination":
        kind = "add_backup_owner"
        title = "Add backup owner on dependent module"
        summary = (
            f"Nominate a second owner path so {finding.source_module_key} / "
            f"{finding.target_module_key} are not solely bridged by weak coordination."
        )
        verdict = "UNKNOWN"
    else:
        kind = "publish_codeowners"
        title = "Publish CODEOWNERS for dependent modules"
        summary = (
            f"Publish durable ownership for {finding.source_module_key} and "
            f"{finding.target_module_key} so authority and communication stay aligned."
        )
        verdict = "SUPPORTED"
    return RepairProposal(
        repair_id=f"repair:faultline:{finding_key}",
        finding_kind="faultline",
        finding_key=finding_key,
        title=title,
        repair_kind=kind,
        summary=summary,
        verdict=verdict,
        evidence_ids=evidence_ids,
        limitations=(
            "Repairs are process obligations, not personnel scores.",
            "Closure is proven by re-running faultline analysis on the overlayed snapshot.",
        ),
    )


def _faultline_key(finding: FaultlineFinding) -> str:
    return (
        f"{finding.source_module_key}|{finding.target_module_key}|"
        f"{finding.source_owner_key}|{finding.target_owner_key}"
    )


def _apply_gap_closure(bundle: CanonicalBundle, phantom_key: str) -> CanonicalBundle:
    nodes: list[NodeRow] = []
    for node in bundle.nodes:
        if node.canonical_key == phantom_key and node.label == "Phantom":
            nodes.append(
                node.model_copy(
                    update={
                        "label": "Artifact",
                        "path_key": path_key("Artifact", node.id),
                        "evidence_class": EvidenceClass.OBSERVED,
                        "properties": {
                            **node.properties,
                            "artifact_kind": "approval",
                            "repair_applied": True,
                            "reason": "repair_ledger_recorded_approval",
                        },
                    }
                )
            )
        else:
            nodes.append(node)
    return bundle.model_copy(
        update={
            "nodes": tuple(nodes),
            "limitations": tuple(
                dict.fromkeys(
                    (
                        *bundle.limitations,
                        "At least one gap was closed via Coordination Repair Ledger overlay.",
                    )
                )
            ),
        }
    )


def _apply_owner_bridge(
    bundle: CanonicalBundle,
    source_owner_key: str,
    target_owner_key: str,
    repair_id: str,
) -> CanonicalBundle:
    by_key = {node.canonical_key: node for node in bundle.nodes}
    source = by_key.get(source_owner_key)
    target = by_key.get(target_owner_key)
    if source is None or target is None:
        return bundle
    left, right = sorted((source, target), key=lambda node: node.id)
    evidence = _repair_evidence(
        bundle,
        repair_id,
        subject_key=source_owner_key,
        object_key=target_owner_key,
        predicate="repair_owner_bridge",
    )
    edge_id = stable_edge_id(
        bundle.dataset_id,
        "COMMUNICATES",
        left.id,
        right.id,
        repair_id,
    )
    if any(edge.id == edge_id for edge in bundle.edges):
        return bundle
    edge = EdgeRow(
        id=edge_id,
        canonical_key=f"communicates:repair:{repair_id.split(':', maxsplit=1)[-1]}",
        source_id=left.id,
        target_id=right.id,
        rel_type="COMMUNICATES",
        evidence_class=EvidenceClass.OBSERVED,
        confidence=90,
        properties={
            "interaction_count": 8,
            "repair_applied": True,
            "repair_id": repair_id,
        },
        evidence_ids=(evidence.evidence_id,),
    )
    return bundle.model_copy(
        update={
            "edges": (*bundle.edges, edge),
            "evidence": (*bundle.evidence, evidence),
            "limitations": tuple(
                dict.fromkeys(
                    (
                        *bundle.limitations,
                        "At least one faultline was addressed via Repair Ledger owner bridge overlay.",
                    )
                )
            ),
        }
    )


def _apply_backup_owner(
    bundle: CanonicalBundle,
    module_key: str,
    owner_key: str,
    repair_id: str,
) -> CanonicalBundle:
    by_key = {node.canonical_key: node for node in bundle.nodes}
    module = by_key.get(module_key)
    owner = by_key.get(owner_key)
    if module is None or owner is None:
        return bundle
    evidence = _repair_evidence(
        bundle,
        repair_id,
        subject_key=owner_key,
        object_key=module_key,
        predicate="repair_backup_owner",
    )
    edge_id = stable_edge_id(
        bundle.dataset_id,
        "OWNS",
        owner.id,
        module.id,
        repair_id,
    )
    if any(edge.id == edge_id for edge in bundle.edges):
        return bundle
    edge = EdgeRow(
        id=edge_id,
        canonical_key=f"owns:repair:{repair_id.split(':', maxsplit=1)[-1]}",
        source_id=owner.id,
        target_id=module.id,
        rel_type="OWNS",
        evidence_class=EvidenceClass.OBSERVED,
        confidence=85,
        properties={
            "authority": "repair_ledger_backup_owner",
            "authority_rank": 70,
            "repair_applied": True,
            "repair_id": repair_id,
        },
        evidence_ids=(evidence.evidence_id,),
    )
    return bundle.model_copy(
        update={
            "edges": (*bundle.edges, edge),
            "evidence": (*bundle.evidence, evidence),
            "limitations": tuple(
                dict.fromkeys(
                    (
                        *bundle.limitations,
                        "At least one ownership repair was applied via Repair Ledger overlay.",
                    )
                )
            ),
        }
    )


def _repair_evidence(
    bundle: CanonicalBundle,
    repair_id: str,
    *,
    subject_key: str,
    object_key: str,
    predicate: str,
) -> EvidenceRecord:
    payload = canonical_json(
        {
            "dataset_id": bundle.dataset_id,
            "object_key": object_key,
            "predicate": predicate,
            "repair_id": repair_id,
            "subject_key": subject_key,
        }
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return EvidenceRecord(
        evidence_id=f"evidence:{digest}",
        run_id=f"repairs:{bundle.dataset_id}",
        source_type="repair_ledger",
        source_uri=f"xray://repairs/{repair_id}",
        source_record_id=repair_id,
        observed_epoch=0,
        subject_key=subject_key,
        predicate=predicate,
        object_key=object_key,
        evidence_class=EvidenceClass.OBSERVED,
        confidence=90,
        extraction_method="coordination_repair_ledger",
        content_sha256=digest,
        redacted_excerpt="",
        metadata_json=payload,
    )


__all__ = [
    "ApprovedRepair",
    "RepairProposal",
    "apply_approved_repairs",
    "propose_repairs",
    "verify_repair",
    "with_status",
]
