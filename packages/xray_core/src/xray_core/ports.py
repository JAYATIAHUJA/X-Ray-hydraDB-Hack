from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Literal, Protocol

from pydantic import Field, model_validator

from .models import (
    EdgeRow,
    EndpointExpectation,
    EvidenceRecord,
    ExecutionStatus,
    NodeRow,
    QuerySpec,
    WriteBatchSpec,
    XrayModel,
)


class PathRecord(XrayModel):
    source_path_key: str = Field(pattern=r"^[a-z]+:[0-9]{20}$")
    target_path_key: str = Field(pattern=r"^[a-z]+:[0-9]{20}$")
    node_ids: tuple[int, ...] = Field(min_length=2)
    node_path_keys: tuple[str, ...] = Field(min_length=2)
    path_cost: float
    path_weight: float

    @model_validator(mode="after")
    def validate_path_shape(self) -> PathRecord:
        if len(self.node_ids) != len(self.node_path_keys):
            raise ValueError("node_ids and node_path_keys must have the same length")
        if self.source_path_key != self.node_path_keys[0]:
            raise ValueError("source_path_key must match the first node path_key")
        if self.target_path_key != self.node_path_keys[-1]:
            raise ValueError("target_path_key must match the last node path_key")
        return self


class EndpointResolution(XrayModel):
    expectation: EndpointExpectation
    status: Literal["resolved", "missing", "identity_mismatch"]
    observed_hydra_id: int | None = None
    observed_canonical_key: str | None = None


class PairEvaluation(XrayModel):
    source_path_key: str = Field(pattern=r"^[a-z]+:[0-9]{20}$")
    target_path_key: str = Field(pattern=r"^[a-z]+:[0-9]{20}$")
    source_resolution: EndpointResolution
    target_resolution: EndpointResolution
    status: ExecutionStatus
    returned_rows: int = Field(strict=True, ge=0)
    query_names: tuple[str, ...]


class PathBatchResult(XrayModel):
    query: str = Field(min_length=1)
    requested_pairs: frozenset[tuple[str, str]]
    paths: tuple[PathRecord, ...]
    pair_evaluations: tuple[PairEvaluation, ...]
    complete: bool
    truncated: bool
    duration_ms: float = Field(ge=0)
    error: str | None = None

    @model_validator(mode="after")
    def validate_completion_state(self) -> PathBatchResult:
        if self.complete and (self.truncated or self.error is not None):
            raise ValueError("complete results cannot be truncated or contain an error")
        evaluated = {
            (evaluation.source_path_key, evaluation.target_path_key)
            for evaluation in self.pair_evaluations
        }
        if evaluated != set(self.requested_pairs):
            raise ValueError("pair_evaluations must cover every requested pair exactly")
        return self


class EvidenceRepository(Protocol):
    def get(self, evidence_id: str) -> EvidenceRecord | None: ...

    def list(self) -> tuple[EvidenceRecord, ...]: ...

    def limitations(self) -> tuple[str, ...]: ...


class GraphGateway(Protocol):
    def run(self, query: QuerySpec) -> list[dict[str, object]]: ...

    def run_batch(self, batch: WriteBatchSpec) -> list[dict[str, object]]: ...

    def paths(
        self,
        query: QuerySpec,
        requested_pairs: set[tuple[str, str]],
        expected_endpoints: Mapping[str, EndpointExpectation],
    ) -> PathBatchResult: ...


class SnapshotRepository(Protocol):
    def nodes(self, label: str | None = None) -> tuple[NodeRow, ...]: ...

    def edges(self, rel_type: str | None = None) -> tuple[EdgeRow, ...]: ...

    def evidence(self, ids: Collection[str]) -> tuple[EvidenceRecord, ...]: ...

    def limitations(self) -> tuple[str, ...]: ...


__all__ = [
    "EndpointExpectation",
    "EndpointResolution",
    "EvidenceRepository",
    "GraphGateway",
    "PairEvaluation",
    "PathBatchResult",
    "PathRecord",
    "SnapshotRepository",
]
