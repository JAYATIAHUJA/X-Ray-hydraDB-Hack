from __future__ import annotations

import json
from pathlib import Path

from xray_analytics import (
    bus_factor_impact,
    communication_asymmetries,
    directed_communication_graph,
    faultlines,
    gap_findings,
    ghost_scores,
)
from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_ingest.pipeline import build_bundle

FIXTURE_ROOT = Path(__file__).parents[2] / "data" / "fixtures" / "xray-demo"


def demo_bundle():
    records: list[CanonicalRecord] = []
    for name in ("directory.json", "events.json", "git_facts.json"):
        records.extend(
            CanonicalRecord.model_validate(payload)
            for payload in json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
        )
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    contracts = SequenceContractSet.model_validate(
        {
            "contracts": manifest["sequence_contracts"],
            "limitations": manifest["limitations"],
        }
    )
    return build_bundle(records, contracts, "xray-demo-v1")


def test_ghost_scores_surface_structural_gap_from_communication_paths() -> None:
    scores = ghost_scores(demo_bundle(), max_len=4)

    maya = next(score for score in scores if score.person_key == "person:maya-chen")

    assert scores[0].person_key == "person:maya-chen"
    assert maya.display_name == "Maya Chen"
    assert maya.role_rank == 1
    assert maya.structural_rank == 1
    assert maya.formal_rank > maya.structural_rank
    assert maya.rank_gap > 0
    assert maya.sampled_centrality > 0


def test_directed_projection_preserves_sender_recipient_asymmetry() -> None:
    bundle = demo_bundle()
    graph = directed_communication_graph(bundle)

    assert "person:maya-chen" in graph["person:alex-rivera"]
    assert "person:alex-rivera" not in graph["person:maya-chen"]
    communication = next(edge for edge in bundle.edges if edge.rel_type == "COMMUNICATES")
    directional = bundle.model_copy(
        update={
            "edges": tuple(
                edge.model_copy(update={"properties": {**edge.properties, "reply_weight": 4}})
                if edge.id == communication.id
                else edge
                for edge in bundle.edges
            )
        }
    )
    assert communication_asymmetries(directional, min_replies=1, min_ratio=2)


def test_bus_factor_counts_pairs_lost_within_the_bounded_sample() -> None:
    impact = bus_factor_impact(demo_bundle(), "person:maya-chen", max_len=4)

    assert impact.person_key == "person:maya-chen"
    assert impact.reachable_pairs_before > 0
    assert impact.pairs_lost_without_person > 0
    assert impact.pairs_lost_without_person <= impact.reachable_pairs_before


def test_faultlines_find_dependency_without_owner_communication() -> None:
    findings = faultlines(demo_bundle(), max_len=4, min_owner_confidence=50)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.source_module_key == "module:payments-api"
    assert finding.target_module_key == "module:ledger-worker"
    assert finding.source_owner_key == "person:maya-chen"
    assert finding.target_owner_key == "person:theo-brooks"
    assert finding.dependency_weight == 12
    assert finding.communication_distance is None
    assert finding.tier == "no_path"
    assert finding.severity == 12


def test_gap_findings_summarize_phantom_chain_neighbors() -> None:
    findings = gap_findings(demo_bundle())

    assert len(findings) == 1
    gap = findings[0]
    assert gap.phantom_key == "artifact:missing-approval"
    assert gap.expected_kind == "approval"
    assert gap.reason == "required_sequence_step_missing"
    assert gap.inferred_epoch == 1736003600
    assert gap.predecessor_keys == ("artifact:directive",)
    assert gap.successor_keys == ("artifact:code-change",)


def test_repair_ledger_closes_gap_and_faultline() -> None:
    from xray_analytics import apply_approved_repairs, propose_repairs, verify_repair
    from xray_analytics.repairs import ApprovedRepair

    bundle = demo_bundle()
    proposals = {item.repair_id: item for item in propose_repairs(bundle)}
    gap = next(item for item in proposals.values() if item.finding_kind == "gap")
    fault = next(item for item in proposals.values() if item.finding_kind == "faultline")

    after_gap = apply_approved_repairs(
        bundle,
        (
            ApprovedRepair(
                repair_id=gap.repair_id,
                repair_kind=gap.repair_kind,
                finding_kind=gap.finding_kind,
                finding_key=gap.finding_key,
                payload={"phantom_key": gap.finding_key},
            ),
        ),
    )
    assert gap_findings(after_gap) == ()
    assert verify_repair(after_gap, gap)[0] is True

    parts = fault.finding_key.split("|")
    after_fault = apply_approved_repairs(
        bundle,
        (
            ApprovedRepair(
                repair_id=fault.repair_id,
                repair_kind=fault.repair_kind,
                finding_kind=fault.finding_kind,
                finding_key=fault.finding_key,
                payload={
                    "source_owner_key": parts[2],
                    "target_owner_key": parts[3],
                },
            ),
        ),
    )
    assert faultlines(after_fault) == ()
    assert verify_repair(after_fault, fault)[0] is True
