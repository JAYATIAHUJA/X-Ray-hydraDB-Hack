from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from xray_core.models import AnalysisStatus, SequenceContractSet


class HydraHealthResponse(BaseModel):
    status: str
    configured: bool
    database: str | None
    uri: str | None
    detail: str
    graph_loaded: bool = False
    node_count: int | None = None
    edge_count: int | None = None


class HealthResponse(BaseModel):
    status: str
    hydra: HydraHealthResponse
    read_only: bool
    imports_enabled: bool


class LoadReportResponse(BaseModel):
    snapshot_id: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    attempted_batches: int = Field(ge=0)
    completed_batches: int = Field(ge=0)
    resumed_batches: int = Field(ge=0)
    failed_batches: tuple[str, ...]
    graph_fingerprint: str


class HydraSeedResponse(BaseModel):
    status: str
    detail: str
    hydra: HydraHealthResponse
    report: LoadReportResponse | None = None


class SnapshotResponse(BaseModel):
    snapshot_id: str
    dataset_id: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    limitations: tuple[str, ...]


class AvailableSnapshot(BaseModel):
    """A corpus the API can switch to without re-ingesting."""

    name: str
    kind: Literal["snapshot", "fixture"]
    dataset_id: str | None = None
    active: bool = False


class ActivateSnapshotRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")


class GraphNode(BaseModel):
    key: str
    name: str
    title: str
    team: str
    official_size: int = Field(gt=0)
    actual_size: int = Field(gt=0)
    selected: bool = False


class GraphEdge(BaseModel):
    source: str
    target: str
    strength: str


class GraphResponse(BaseModel):
    snapshot_id: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


class WhatIfSummary(BaseModel):
    """Result of re-scoring the Ghost sample with the given people removed."""

    excluded_person_keys: tuple[str, ...]
    sampled_pairs_before: int
    sampled_pairs_after: int
    pairs_lost: int
    max_len: int


class EngineComparison(BaseModel):
    """Engine round trip vs the in-process bounded-BFS baseline for the same question."""

    engine_ms: float | None
    client_ms: float
    client_method: str
    sampled_people: int
    engine_round_trips: int
    client_equivalent_round_trips: int


class LensEnvelope(BaseModel):
    snapshot_id: str
    analysis_status: AnalysisStatus
    status_explanation: str
    limitations: tuple[str, ...]
    findings: tuple[dict[str, object], ...]
    source: str = "fixture"
    degraded_reason: str | None = None
    executed_query: dict[str, object] | None = None
    what_if: WhatIfSummary | None = None
    comparison: EngineComparison | None = None
    total_findings: int | None = None


class GapPathRequest(BaseModel):
    source_artifact_key: str = Field(min_length=1)
    target_artifact_key: str = Field(min_length=1)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class EvidenceDecisionResponse(BaseModel):
    person_key: str
    source_type: str
    source_record_id: str
    authority: str
    observed_epoch: int = Field(ge=0)
    valid_from_epoch: int | None = Field(default=None, ge=0)
    valid_until_epoch: int | None = Field(default=None, ge=0)
    confidence: int = Field(ge=0, le=100)
    selected: bool
    reason: str


class QuestionResponse(BaseModel):
    snapshot_id: str
    question: str
    intent: str
    status: Literal["answered", "not_found", "no_answer", "unsupported"]
    answer: str
    subject_key: str | None
    person_keys: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    paths: tuple[tuple[str, ...], ...]
    confidence: int | None = Field(default=None, ge=0, le=100)
    answer_kind: Literal["direct", "multi_hop", "abstention", "unsupported"]
    reasoning: tuple[str, ...]
    limitations: tuple[str, ...]
    conflicts: tuple[EvidenceDecisionResponse, ...] = ()
    trust_explanation: str | None = None
    evidence: tuple[dict[str, object], ...] = ()
    source: Literal["fixture", "hydradb"] = "fixture"
    degraded_reason: str | None = None
    executed_query: dict[str, object] | None = None
    engine_ms: float | None = Field(default=None, ge=0)
    round_trips: int = Field(default=0, ge=0)


class IdentityMemberResponse(BaseModel):
    person_key: str
    display_name: str
    source_identity: str
    source_type: str


class IdentityCandidateResponse(BaseModel):
    candidate_id: str
    proposed_person_key: str
    proposed_display_name: str
    confidence: int = Field(ge=0, le=100)
    signals: tuple[str, ...]
    members: tuple[IdentityMemberResponse, ...]
    status: Literal["pending", "accepted", "rejected"]
    projected_node_reduction: int = Field(ge=0)
    affected_edge_count: int = Field(ge=0)
    duplicate_relationships_removed: int = Field(ge=0)
    limitations: tuple[str, ...]


class IdentityDecisionRequest(BaseModel):
    decision: Literal["accepted", "rejected", "pending"]


class ImportRequest(BaseModel):
    """Browser-friendly JSON form of the supported offline export inputs."""

    dataset_id: str = Field(min_length=1, max_length=120)
    directory: tuple[dict[str, object], ...] = ()
    identity_map: dict[str, str] = {}
    mbox: tuple[str, ...] = ()
    jira_csv: str | None = None
    git_log: str | None = None
    module_prefixes: dict[str, str] = {}
    slack_exports: dict[str, tuple[dict[str, object], ...]] = {}
    channel_modules: dict[str, tuple[str, ...]] = {}
    message_modules: dict[str, tuple[str, ...]] = {}
    confluence_xml: str | None = None
    github_csv: str | None = None
    sequence_contracts: SequenceContractSet = Field(default_factory=SequenceContractSet)


class ProblemDetail(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    code: str
    retryable: bool = False


__all__ = [
    "EngineComparison",
    "GapPathRequest",
    "GraphEdge",
    "GraphNode",
    "GraphResponse",
    "HealthResponse",
    "HydraHealthResponse",
    "HydraSeedResponse",
    "IdentityCandidateResponse",
    "IdentityDecisionRequest",
    "IdentityMemberResponse",
    "ImportRequest",
    "LensEnvelope",
    "LoadReportResponse",
    "ProblemDetail",
    "QuestionRequest",
    "QuestionResponse",
    "SnapshotResponse",
    "WhatIfSummary",
]
