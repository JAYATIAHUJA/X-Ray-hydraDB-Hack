from __future__ import annotations

import pytest
from pydantic import ValidationError
from xray_core.models import (
    AnalysisStatus,
    CanonicalBundle,
    CanonicalRecord,
    EdgeRow,
    EvidenceClass,
    EvidenceRecord,
    ExecutionStatus,
    FaultlineScoreInputs,
    GapDerivation,
    LoadReport,
    NodeRow,
    NormalizedPosition,
    QuerySpec,
    ReachabilityStatus,
    RetentionPlan,
    RetentionResult,
    SequenceContract,
    SequenceContractSet,
    SequenceStep,
    SnapshotManifest,
    WriteBatchSpec,
)

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def person_node(*, node_id: int = 1, evidence_ids: tuple[str, ...] = ()) -> NodeRow:
    return NodeRow(
        id=node_id,
        canonical_key="person:test",
        path_key=f"person:{node_id:020d}",
        label="Person",
        evidence_class="observed",
        confidence=100,
        properties={"role_rank": 1},
        evidence_ids=evidence_ids,
    )


def evidence_record(evidence_id: str = "evidence:test") -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id="canonicalize:test",
        source_type="fixture",
        source_uri="fixture://test/record",
        source_record_id="record",
        observed_epoch=1,
        subject_key="person:test",
        predicate="directory_person",
        object_key="person:test",
        evidence_class="observed",
        confidence=100,
        extraction_method="canonical_record",
        content_sha256=EMPTY_SHA256,
        redacted_excerpt="",
        metadata_json="{}",
    )


def test_node_rejects_nonprimitive_hydra_property() -> None:
    with pytest.raises(ValidationError, match="Hydra properties"):
        NodeRow(
            id=1,
            canonical_key="person:test",
            path_key="person:00000000000000000001",
            label="Person",
            evidence_class="observed",
            confidence=100,
            properties={"teams": [1, 2]},
            evidence_ids=(),
        )


def canonical_record_payload() -> dict[str, object]:
    return {
        "source": "fixture",
        "external_id": "test",
        "kind": "directory_person",
        "occurred_at_epoch": 0,
        "author_external_id": None,
        "parent_external_id": None,
        "subjects": ["person:test"],
        "content_sha256": EMPTY_SHA256,
        "content": None,
        "metadata": {},
    }


def test_canonical_record_rejects_unknown_fields() -> None:
    payload = {**canonical_record_payload(), "unexpected": "value"}

    with pytest.raises(ValidationError):
        CanonicalRecord.model_validate(payload)


@pytest.mark.parametrize("unsafe_value", ([1, 2], {"unsafe": True}, None))
def test_canonical_record_rejects_nonprimitive_metadata(unsafe_value: object) -> None:
    payload = canonical_record_payload()
    payload["metadata"] = {"unsafe": unsafe_value}

    with pytest.raises(ValidationError, match="Hydra properties"):
        CanonicalRecord.model_validate(payload)


def test_node_path_key_must_match_its_label_and_id() -> None:
    with pytest.raises(ValidationError, match="path_key"):
        NodeRow(
            id=7,
            canonical_key="person:test",
            path_key="person:00000000000000000008",
            label="Person",
            evidence_class="observed",
            confidence=100,
            properties={},
            evidence_ids=(),
        )


def test_sequence_contract_rejects_non_increasing_or_duplicate_steps() -> None:
    with pytest.raises(ValidationError, match="strictly increasing"):
        SequenceContract(
            contract_id="contract:test",
            contract_kind="contiguous_sequence",
            sequence_key="test-sequence",
            steps=(
                SequenceStep(ordinal=1, canonical_key="artifact:later", artifact_kind="event"),
                SequenceStep(ordinal=0, canonical_key="artifact:earlier", artifact_kind="event"),
            ),
            source_uri="fixture://test/contract",
            content_sha256=EMPTY_SHA256,
        )

    with pytest.raises(ValidationError, match="duplicate canonical_key"):
        SequenceContract(
            contract_id="contract:test",
            contract_kind="contiguous_sequence",
            sequence_key="test-sequence",
            steps=(
                SequenceStep(ordinal=0, canonical_key="artifact:same", artifact_kind="event"),
                SequenceStep(ordinal=1, canonical_key="artifact:same", artifact_kind="event"),
            ),
            source_uri="fixture://test/contract",
            content_sha256=EMPTY_SHA256,
        )


def test_sequence_contract_set_rejects_duplicate_contract_ids() -> None:
    contract = SequenceContract(
        contract_id="contract:test",
        contract_kind="contiguous_sequence",
        sequence_key="test-sequence",
        steps=(
            SequenceStep(ordinal=0, canonical_key="artifact:a", artifact_kind="event"),
            SequenceStep(ordinal=1, canonical_key="artifact:b", artifact_kind="event"),
        ),
        source_uri="fixture://test/contract",
        content_sha256=EMPTY_SHA256,
    )

    with pytest.raises(ValidationError, match="duplicate contract_id"):
        SequenceContractSet(contracts=(contract, contract))


def test_sequence_step_rejects_inverted_epoch_bounds() -> None:
    with pytest.raises(ValidationError, match="earliest_epoch"):
        SequenceStep(
            ordinal=0,
            canonical_key="artifact:test",
            artifact_kind="event",
            earliest_epoch=20,
            latest_epoch=10,
        )


def test_bundle_rejects_dangling_edge_endpoints() -> None:
    evidence = evidence_record()
    node = person_node(evidence_ids=(evidence.evidence_id,))
    dangling_edge = EdgeRow(
        id=3,
        canonical_key="reporting:test:missing",
        source_id=node.id,
        target_id=2,
        rel_type="REPORTS_TO",
        evidence_class="observed",
        confidence=100,
        properties={},
        evidence_ids=(evidence.evidence_id,),
    )

    with pytest.raises(ValidationError, match="missing endpoint"):
        CanonicalBundle(
            dataset_id="test",
            nodes=(node,),
            edges=(dangling_edge,),
            evidence=(evidence,),
        )


def test_bundle_rejects_unknown_evidence_references() -> None:
    with pytest.raises(ValidationError, match="unknown evidence"):
        CanonicalBundle(
            dataset_id="test",
            nodes=(person_node(evidence_ids=("evidence:missing",)),),
            edges=(),
            evidence=(),
        )


def test_bundle_rejects_an_id_reused_by_a_node_and_edge() -> None:
    evidence = evidence_record()
    node = person_node(evidence_ids=(evidence.evidence_id,))
    edge = EdgeRow(
        id=node.id,
        canonical_key="reporting:test:self",
        source_id=node.id,
        target_id=node.id,
        rel_type="REPORTS_TO",
        evidence_class="observed",
        confidence=100,
        properties={},
        evidence_ids=(evidence.evidence_id,),
    )

    with pytest.raises(ValidationError, match="node and edge ID"):
        CanonicalBundle(
            dataset_id="test",
            nodes=(node,),
            edges=(edge,),
            evidence=(evidence,),
        )


@pytest.mark.parametrize("invalid_id", (True, "1", 1.5, 0, 2**63))
def test_graph_ids_are_strict_positive_signed_63_bit(invalid_id: object) -> None:
    payload = person_node().model_dump()
    payload["id"] = invalid_id

    with pytest.raises(ValidationError):
        NodeRow.model_validate(payload)


@pytest.mark.parametrize("invalid_coordinate", (True, "0.5"))
def test_normalized_positions_reject_coerced_coordinates(invalid_coordinate: object) -> None:
    with pytest.raises(ValidationError):
        NormalizedPosition(x=invalid_coordinate, y=0.5)  # type: ignore[arg-type]


def test_remaining_stable_models_construct_with_bounded_values() -> None:
    query = QuerySpec(
        name="bounded",
        statement="MATCH (n) RETURN n LIMIT $limit",
        parameters={"limit": 1},
        max_len=4,
        result_limit=10,
    )
    evidence = evidence_record()
    assert AnalysisStatus.COMPLETE == "complete"
    assert ReachabilityStatus.INDETERMINATE == "indeterminate"
    assert ExecutionStatus.FAILED == "failed"
    assert EvidenceClass.OBSERVED == "observed"
    assert NormalizedPosition(x=0.25, y=0.75).x == 0.25
    assert WriteBatchSpec(name="nodes", statement="UNWIND $rows", rows=({"id": 1},)).rows
    assert GapDerivation(phantoms=(), edges=(), evidence=(evidence,), limitations=()).evidence
    assert (
        LoadReport(
            snapshot_id="snapshot",
            node_count=1,
            edge_count=0,
            attempted_batches=1,
            completed_batches=1,
            resumed_batches=0,
            failed_batches=(),
            graph_fingerprint="fingerprint",
            verification_queries=(query,),
        ).completed_batches
        == 1
    )
    assert (
        FaultlineScoreInputs(
            dependency_weight_percentile=0.5,
            coordination_risk=0.5,
            min_owner_confidence=0.5,
            module_criticality=0.5,
            evidence_weight=0.5,
        ).coordination_risk
        == 0.5
    )
    assert SnapshotManifest(
        snapshot_id="snapshot",
        dataset_id="dataset",
        schema_version="1.0.0",
        content_sha256=EMPTY_SHA256,
        row_counts={"nodes": 1},
        file_sha256={"nodes.parquet": EMPTY_SHA256},
    ).row_counts == {"nodes": 1}
    plan = RetentionPlan(
        tenant_id="tenant",
        source_snapshot_id="blue",
        green_graph_id="green",
        green_object_prefix="tenant/green",
        retained_evidence_sha256=(EMPTY_SHA256,),
        deleted_evidence_sha256=(),
        legal_hold=False,
        confirmation_sha256=EMPTY_SHA256,
    )
    assert plan.green_graph_id == "green"
    assert RetentionResult(
        active_snapshot_id="green",
        pointer_swapped=True,
        local_purge_complete=True,
        residual_graph_objects=False,
        rollback_performed=False,
        verification_sha256=EMPTY_SHA256,
    ).pointer_swapped


def test_query_parameters_accept_flat_arrays_but_reject_nested_values() -> None:
    query = QuerySpec(
        name="selectors",
        statement="RETURN $values",
        parameters={"values": [1, "two"]},
        max_len=None,
        result_limit=None,
    )
    assert query.parameters == {"values": (1, "two")}
    with pytest.raises(ValidationError, match="Hydra properties"):
        QuerySpec(
            name="unsafe",
            statement="RETURN $value",
            parameters={"value": [[1]]},
            max_len=None,
            result_limit=None,
        )
    with pytest.raises(ValidationError, match="Hydra properties"):
        WriteBatchSpec(name="unsafe", statement="UNWIND $rows", rows=({"value": None},))
