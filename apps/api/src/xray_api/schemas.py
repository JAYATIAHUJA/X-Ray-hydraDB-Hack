from __future__ import annotations

from pydantic import BaseModel, Field
from xray_core.models import AnalysisStatus


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
    "ImportRequest",
    "LensEnvelope",
    "LoadReportResponse",
    "ProblemDetail",
    "SnapshotResponse",
    "WhatIfSummary",
]
