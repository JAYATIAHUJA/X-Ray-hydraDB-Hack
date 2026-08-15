from __future__ import annotations

import json
import math
from collections.abc import Iterable
from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_HYDRA_ID = 2**63 - 1
MIN_HYDRA_INTEGER = -(2**63)
SHA256_PATTERN = r"^[0-9a-f]{64}$"

type Scalar = int | float | bool | str
type HydraId = Annotated[int, Field(strict=True, gt=0, le=MAX_HYDRA_ID)]
type NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
type Confidence = Annotated[int, Field(strict=True, ge=0, le=100)]
type UnitFloat = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]


def _validate_nonempty_strings(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} must contain only non-empty strings")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


def _validate_hydra_scalar(value: object, field_name: str) -> Scalar:
    if type(value) not in {int, float, bool, str}:
        raise ValueError(f"Hydra properties in {field_name} must be int, float, bool, or string")
    if type(value) is int and not MIN_HYDRA_INTEGER <= value <= MAX_HYDRA_ID:
        raise ValueError(f"Hydra integer in {field_name} is outside the signed 64-bit range")
    if type(value) is float and not math.isfinite(value):
        raise ValueError(f"Hydra float in {field_name} must be finite")
    return value  # type: ignore[return-value]


def _validate_scalar_mapping(value: object, field_name: str) -> dict[str, Scalar]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a mapping")

    normalized: dict[str, Scalar] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        normalized[key] = _validate_hydra_scalar(item, field_name)
    return dict(sorted(normalized.items()))


class XrayModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class EvidenceClass(StrEnum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    DEMO_GROUND_TRUTH = "demo_ground_truth"


class AnalysisStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


class ReachabilityStatus(StrEnum):
    REACHABLE = "reachable"
    NOT_REACHABLE_WITHIN_BOUND = "not_reachable_within_bound"
    INDETERMINATE = "indeterminate"


class ExecutionStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class CanonicalRecord(XrayModel):
    source: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    occurred_at_epoch: NonNegativeInt
    author_external_id: str | None
    parent_external_id: str | None
    subjects: tuple[str, ...]
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    content: str | None
    metadata: dict[str, Scalar]

    @field_validator("subjects")
    @classmethod
    def validate_subjects(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_nonempty_strings(value, "subjects")

    @field_validator("metadata", mode="before")
    @classmethod
    def validate_metadata(cls, value: object) -> dict[str, Scalar]:
        return _validate_scalar_mapping(value, "metadata")


class SequenceStep(XrayModel):
    ordinal: NonNegativeInt
    canonical_key: str = Field(min_length=1)
    artifact_kind: str = Field(min_length=1)
    required: bool = True
    earliest_epoch: NonNegativeInt | None = None
    latest_epoch: NonNegativeInt | None = None

    @model_validator(mode="after")
    def validate_epoch_bounds(self) -> Self:
        if (
            self.earliest_epoch is not None
            and self.latest_epoch is not None
            and self.earliest_epoch > self.latest_epoch
        ):
            raise ValueError("earliest_epoch must be less than or equal to latest_epoch")
        return self


class SequenceContract(XrayModel):
    contract_id: str = Field(min_length=1)
    contract_kind: Literal["contiguous_sequence", "required_audit_transition"]
    sequence_key: str = Field(min_length=1)
    steps: tuple[SequenceStep, ...] = Field(min_length=2)
    source_uri: str = Field(min_length=1)
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    limitations: tuple[str, ...] = ()

    @field_validator("limitations")
    @classmethod
    def validate_limitations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_nonempty_strings(value, "limitations")

    @model_validator(mode="after")
    def validate_steps(self) -> Self:
        ordinals = [step.ordinal for step in self.steps]
        if len(ordinals) != len(set(ordinals)):
            raise ValueError("steps contain a duplicate ordinal")
        if any(current >= following for current, following in pairwise(ordinals)):
            raise ValueError("step ordinals must be strictly increasing")

        canonical_keys = [step.canonical_key for step in self.steps]
        if len(canonical_keys) != len(set(canonical_keys)):
            raise ValueError("steps contain a duplicate canonical_key")
        return self


class SequenceContractSet(XrayModel):
    contracts: tuple[SequenceContract, ...] = ()
    limitations: tuple[str, ...] = ()

    @field_validator("limitations")
    @classmethod
    def validate_limitations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_nonempty_strings(value, "limitations")

    @model_validator(mode="after")
    def validate_contract_ids(self) -> Self:
        contract_ids = [contract.contract_id for contract in self.contracts]
        if len(contract_ids) != len(set(contract_ids)):
            raise ValueError("contracts contain a duplicate contract_id")
        return self


class EvidenceRecord(XrayModel):
    evidence_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_uri: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    observed_epoch: NonNegativeInt
    subject_key: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object_key: str = Field(min_length=1)
    evidence_class: EvidenceClass
    confidence: Confidence
    extraction_method: str = Field(min_length=1)
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    redacted_excerpt: str
    metadata_json: str

    @field_validator("metadata_json")
    @classmethod
    def validate_metadata_json(cls, value: str) -> str:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("metadata_json must contain valid JSON") from error
        if not isinstance(parsed, dict):
            raise ValueError("metadata_json must contain a JSON object")
        return value


class NodeRow(XrayModel):
    id: HydraId
    canonical_key: str = Field(min_length=1)
    path_key: str = Field(min_length=1)
    label: Literal["Person", "Team", "Artifact", "Module", "Phantom"]
    evidence_class: EvidenceClass
    confidence: Confidence
    properties: dict[str, Scalar]
    evidence_ids: tuple[str, ...]

    @field_validator("properties", mode="before")
    @classmethod
    def validate_properties(cls, value: object) -> dict[str, Scalar]:
        return _validate_scalar_mapping(value, "properties")

    @field_validator("evidence_ids")
    @classmethod
    def validate_evidence_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(_validate_nonempty_strings(value, "evidence_ids")))

    @model_validator(mode="after")
    def validate_graph_identity(self) -> Self:
        expected_path_key = f"{self.label.lower()}:{self.id:020d}"
        if self.path_key != expected_path_key:
            raise ValueError(f"path_key must equal {expected_path_key}")

        prefix_by_label = {
            "Person": "person:",
            "Team": "team:",
            "Artifact": "artifact:",
            "Module": "module:",
            "Phantom": "artifact:",
        }
        if not self.canonical_key.startswith(prefix_by_label[self.label]):
            raise ValueError(f"canonical_key does not match the {self.label} label")
        return self


class EdgeRow(XrayModel):
    id: HydraId
    canonical_key: str = Field(min_length=1)
    source_id: HydraId
    target_id: HydraId
    rel_type: Literal[
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
    evidence_class: EvidenceClass
    confidence: Confidence
    properties: dict[str, Scalar]
    evidence_ids: tuple[str, ...]

    @field_validator("properties", mode="before")
    @classmethod
    def validate_properties(cls, value: object) -> dict[str, Scalar]:
        return _validate_scalar_mapping(value, "properties")

    @field_validator("evidence_ids")
    @classmethod
    def validate_evidence_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(_validate_nonempty_strings(value, "evidence_ids")))


class CanonicalBundle(XrayModel):
    dataset_id: str = Field(min_length=1)
    nodes: tuple[NodeRow, ...]
    edges: tuple[EdgeRow, ...]
    evidence: tuple[EvidenceRecord, ...]
    limitations: tuple[str, ...] = ()

    @field_validator("limitations")
    @classmethod
    def validate_limitations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_nonempty_strings(value, "limitations")

    @model_validator(mode="after")
    def validate_references_and_uniqueness(self) -> Self:
        self._require_unique((node.id for node in self.nodes), "node id")
        self._require_unique((node.canonical_key for node in self.nodes), "node canonical_key")
        self._require_unique((node.path_key for node in self.nodes), "node path_key")
        self._require_unique((edge.id for edge in self.edges), "edge id")
        self._require_unique((edge.canonical_key for edge in self.edges), "edge canonical_key")
        self._require_unique(
            (record.evidence_id for record in self.evidence),
            "evidence id",
        )

        node_ids = {node.id for node in self.nodes}
        reused_ids = node_ids & {edge.id for edge in self.edges}
        if reused_ids:
            raise ValueError(
                f"CanonicalBundle contains a node and edge ID collision: {sorted(reused_ids)}"
            )
        for edge in self.edges:
            if edge.source_id not in node_ids or edge.target_id not in node_ids:
                raise ValueError(f"edge {edge.canonical_key} has a missing endpoint")

        evidence_ids = {record.evidence_id for record in self.evidence}
        for node in self.nodes:
            missing = set(node.evidence_ids) - evidence_ids
            if missing:
                raise ValueError(
                    f"{node.canonical_key} references unknown evidence: {sorted(missing)}"
                )
        for edge in self.edges:
            missing = set(edge.evidence_ids) - evidence_ids
            if missing:
                raise ValueError(
                    f"{edge.canonical_key} references unknown evidence: {sorted(missing)}"
                )
        return self

    @staticmethod
    def _require_unique(values: Iterable[int | str], field_name: str) -> None:
        materialized = list(values)
        if len(materialized) != len(set(materialized)):
            raise ValueError(f"CanonicalBundle contains a duplicate {field_name}")


class SnapshotManifest(XrayModel):
    snapshot_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    row_counts: dict[str, NonNegativeInt]
    file_sha256: dict[str, str]

    @field_validator("file_sha256")
    @classmethod
    def validate_file_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        for name, digest in value.items():
            if not name.strip():
                raise ValueError("file_sha256 keys must be non-empty")
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError("file_sha256 values must be lowercase SHA-256 digests")
        return dict(sorted(value.items()))


class NormalizedPosition(XrayModel):
    x: UnitFloat
    y: UnitFloat


class QuerySpec(XrayModel):
    name: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    parameters: dict[str, Scalar]
    max_len: Annotated[int, Field(strict=True, gt=0)] | None
    result_limit: Annotated[int, Field(strict=True, gt=0)] | None

    @field_validator("parameters", mode="before")
    @classmethod
    def validate_parameters(cls, value: object) -> dict[str, Scalar]:
        return _validate_scalar_mapping(value, "parameters")


class EndpointExpectation(XrayModel):
    path_key: str = Field(pattern=r"^[a-z]+:[0-9]{20}$")
    hydra_id: HydraId
    canonical_key: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)


class WriteBatchSpec(XrayModel):
    name: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    rows: tuple[dict[str, Scalar], ...]

    @field_validator("rows", mode="before")
    @classmethod
    def validate_rows(cls, value: object) -> tuple[dict[str, Scalar], ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("rows must be a sequence")
        return tuple(_validate_scalar_mapping(row, "rows") for row in value)


class GapDerivation(XrayModel):
    phantoms: tuple[NodeRow, ...]
    edges: tuple[EdgeRow, ...]
    evidence: tuple[EvidenceRecord, ...]
    limitations: tuple[str, ...]


class LoadReport(XrayModel):
    snapshot_id: str = Field(min_length=1)
    node_count: NonNegativeInt
    edge_count: NonNegativeInt
    attempted_batches: NonNegativeInt
    completed_batches: NonNegativeInt
    resumed_batches: NonNegativeInt
    failed_batches: tuple[str, ...]
    graph_fingerprint: str = Field(min_length=1)
    verification_queries: tuple[QuerySpec, ...]

    @model_validator(mode="after")
    def validate_batch_counts(self) -> Self:
        if self.completed_batches > self.attempted_batches:
            raise ValueError("completed_batches cannot exceed attempted_batches")
        if self.resumed_batches > self.completed_batches:
            raise ValueError("resumed_batches cannot exceed completed_batches")
        return self


class FaultlineScoreInputs(XrayModel):
    dependency_weight_percentile: UnitFloat
    coordination_risk: UnitFloat
    min_owner_confidence: UnitFloat
    module_criticality: UnitFloat
    evidence_weight: UnitFloat


class RetentionPlan(XrayModel):
    tenant_id: str = Field(min_length=1)
    source_snapshot_id: str = Field(min_length=1)
    green_graph_id: str = Field(min_length=1)
    green_object_prefix: str = Field(min_length=1)
    retained_evidence_sha256: tuple[Annotated[str, Field(pattern=SHA256_PATTERN)], ...]
    deleted_evidence_sha256: tuple[Annotated[str, Field(pattern=SHA256_PATTERN)], ...]
    legal_hold: bool
    confirmation_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_evidence_sets(self) -> Self:
        if set(self.retained_evidence_sha256) & set(self.deleted_evidence_sha256):
            raise ValueError("retained and deleted evidence sets must be disjoint")
        return self


class RetentionResult(XrayModel):
    active_snapshot_id: str = Field(min_length=1)
    pointer_swapped: bool
    local_purge_complete: bool
    residual_graph_objects: bool
    rollback_performed: bool
    verification_sha256: str = Field(pattern=SHA256_PATTERN)


__all__ = [
    "MAX_HYDRA_ID",
    "AnalysisStatus",
    "CanonicalBundle",
    "CanonicalRecord",
    "EdgeRow",
    "EndpointExpectation",
    "EvidenceClass",
    "EvidenceRecord",
    "ExecutionStatus",
    "FaultlineScoreInputs",
    "GapDerivation",
    "LoadReport",
    "NodeRow",
    "NormalizedPosition",
    "QuerySpec",
    "ReachabilityStatus",
    "RetentionPlan",
    "RetentionResult",
    "Scalar",
    "SequenceContract",
    "SequenceContractSet",
    "SequenceStep",
    "SnapshotManifest",
    "WriteBatchSpec",
]
