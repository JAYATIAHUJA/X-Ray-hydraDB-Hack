from __future__ import annotations

from xray_analytics import identity_candidates
from xray_api.dependencies import demo_bundle


def test_identity_candidates_explain_members_signals_and_graph_impact() -> None:
    candidates = identity_candidates(demo_bundle())

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.candidate_id == "candidate:sam-ratnaparkhi"
    assert candidate.proposed_person_key == "person:sam-ratnaparkhi"
    assert {member.source_type for member in candidate.members} == {
        "directory",
        "git",
        "slack",
    }
    assert candidate.confidence == 88
    assert candidate.projected_node_reduction == 2
    assert candidate.affected_edge_count == 3
    assert candidate.duplicate_relationships_removed == 2
    assert candidate.status == "pending"


def test_identity_decision_does_not_mutate_the_graph() -> None:
    bundle = demo_bundle()
    accepted = identity_candidates(bundle, {"candidate:sam-ratnaparkhi": "accepted"})[0]

    assert accepted.status == "accepted"
    assert len(bundle.nodes) == 20
    assert all(
        "suggested merge" in item.lower() or "future snapshot" in item.lower()
        for item in accepted.limitations
    )
