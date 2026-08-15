from __future__ import annotations

from pydantic import BaseModel, Field
from xray_core.models import AnalysisStatus


class HealthResponse(BaseModel):
    status: str


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
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
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


class LensEnvelope(BaseModel):
    snapshot_id: str
    analysis_status: AnalysisStatus
    status_explanation: str
    limitations: tuple[str, ...]
    findings: tuple[dict[str, object], ...]


class GapPathRequest(BaseModel):
    source_artifact_key: str = Field(min_length=1)
    target_artifact_key: str = Field(min_length=1)


class ProblemDetail(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    code: str
    retryable: bool = False


__all__ = [
    "GapPathRequest",
    "GraphEdge",
    "GraphNode",
    "GraphResponse",
    "HealthResponse",
    "LensEnvelope",
    "ProblemDetail",
    "SnapshotResponse",
]
