from __future__ import annotations

import math
import time
from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

from xray_core.models import ExecutionStatus, QuerySpec, WriteBatchSpec
from xray_core.ports import (
    EndpointExpectation,
    EndpointResolution,
    PairEvaluation,
    PathBatchResult,
    PathRecord,
)

from .cypher import resolve_path_key_query


class DriverLike(Protocol):
    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, object] | None = None,
    ) -> object: ...


class SessionLike(Protocol):
    def run(self, query: str, parameters: dict[str, object]) -> Iterable[object]: ...


@runtime_checkable
class SessionDriverLike(Protocol):
    def session(self) -> AbstractContextManager[SessionLike]: ...


class GatewayError(RuntimeError):
    """Raised when a HydraDB response cannot be normalized safely."""


class HydraGateway:
    def __init__(self, driver: DriverLike) -> None:
        self.driver = driver

    def run(self, query: QuerySpec) -> list[dict[str, object]]:
        return _execute(self.driver, query.statement, dict(query.parameters))

    def run_batch(self, batch: WriteBatchSpec) -> list[dict[str, object]]:
        return _execute(
            self.driver,
            batch.statement,
            {"rows": [dict(row) for row in batch.rows]},
        )

    def paths(
        self,
        query: QuerySpec,
        requested_pairs: set[tuple[str, str]],
        expected_endpoints: Mapping[str, EndpointExpectation],
    ) -> PathBatchResult:
        started = time.perf_counter()
        normalized_pairs = frozenset(_normalize_pair(*pair) for pair in requested_pairs)
        resolutions = {
            path_key: self._resolve_endpoint(expectation)
            for path_key, expectation in expected_endpoints.items()
        }
        executed = all(
            resolutions[pair[0]].status == "resolved" and resolutions[pair[1]].status == "resolved"
            for pair in normalized_pairs
        )

        paths: tuple[PathRecord, ...] = ()
        error: str | None = None
        returned_rows = 0
        if executed:
            try:
                parsed = [
                    path
                    for row in self.run(query)
                    if (path := _path_record(row)) is not None
                    and _normalize_pair(path.source_path_key, path.target_path_key)
                    in normalized_pairs
                ]
            except Exception as exc:
                error = str(exc)
                parsed = []
            paths = tuple(parsed)
            returned_rows = len(paths)

        limit = query.result_limit or 0
        truncated = bool(limit and returned_rows >= limit)
        evaluations = []
        for source_key, target_key in sorted(normalized_pairs):
            pair_rows = sum(
                1
                for path in paths
                if _normalize_pair(path.source_path_key, path.target_path_key)
                == (source_key, target_key)
            )
            source_resolution = resolutions[source_key]
            target_resolution = resolutions[target_key]
            status = (
                ExecutionStatus.COMPLETE
                if error is None
                and not truncated
                and source_resolution.status == "resolved"
                and target_resolution.status == "resolved"
                else ExecutionStatus.PARTIAL
            )
            evaluations.append(
                PairEvaluation(
                    source_path_key=source_key,
                    target_path_key=target_key,
                    source_resolution=source_resolution,
                    target_resolution=target_resolution,
                    status=status,
                    returned_rows=pair_rows,
                    query_names=("resolve_path_key", query.name),
                )
            )

        return PathBatchResult(
            query=query.statement,
            requested_pairs=normalized_pairs,
            paths=paths,
            pair_evaluations=tuple(evaluations),
            complete=executed and error is None and not truncated,
            truncated=truncated,
            duration_ms=(time.perf_counter() - started) * 1000,
            error=error,
        )

    def _resolve_endpoint(self, expectation: EndpointExpectation) -> EndpointResolution:
        rows = self.run(resolve_path_key_query(expectation))
        if len(rows) != 1:
            return EndpointResolution(expectation=expectation, status="missing")

        row = rows[0]
        observed_id = row.get("id")
        observed_path_key = row.get("path_key")
        observed_canonical_key = row.get("canonical_key")
        observed_dataset_id = row.get("dataset_id")
        if (
            observed_id != expectation.hydra_id
            or observed_path_key != expectation.path_key
            or observed_canonical_key != expectation.canonical_key
            or observed_dataset_id != expectation.dataset_id
        ):
            return EndpointResolution(
                expectation=expectation,
                status="identity_mismatch",
                observed_hydra_id=observed_id if type(observed_id) is int else None,
                observed_canonical_key=(
                    observed_canonical_key if isinstance(observed_canonical_key, str) else None
                ),
            )

        return EndpointResolution(
            expectation=expectation,
            status="resolved",
            observed_hydra_id=expectation.hydra_id,
            observed_canonical_key=expectation.canonical_key,
        )


def _records(result: object) -> list[dict[str, object]]:
    if isinstance(result, tuple) and result:
        result = result[0]
    if not isinstance(result, list):
        raise GatewayError("driver returned an unsupported result shape")
    rows: list[dict[str, object]] = []
    for row in result:
        if isinstance(row, dict):
            rows.append(row)
        elif hasattr(row, "data"):
            data = row.data()
            if not isinstance(data, dict):
                raise GatewayError("driver row data() did not return a mapping")
            rows.append(data)
        else:
            raise GatewayError("driver row is not mapping-like")
    return rows


def _execute(
    driver: DriverLike,
    statement: str,
    parameters: dict[str, object],
) -> list[dict[str, object]]:
    if isinstance(driver, SessionDriverLike):
        with driver.session() as session:
            result = session.run(statement, parameters)
            return _records(list(result))
    return _records(driver.execute_query(statement, parameters_=parameters))


def _path_record(row: Mapping[str, object]) -> PathRecord | None:
    path = row.get("path")
    if path is None:
        return None
    nodes = _path_nodes(path)
    if len(nodes) < 2:
        raise GatewayError("path rows must contain at least two nodes")
    ids = tuple(_node_id(node) for node in nodes)
    path_keys = tuple(_node_path_key(node) for node in nodes)
    path_cost = _finite_float(row.get("pathCost"), "pathCost")
    path_weight = _finite_float(row.get("pathWeight"), "pathWeight")
    return PathRecord(
        source_path_key=path_keys[0],
        target_path_key=path_keys[-1],
        node_ids=ids,
        node_path_keys=path_keys,
        path_cost=path_cost,
        path_weight=path_weight,
    )


def _path_nodes(path: object) -> tuple[object, ...]:
    if isinstance(path, (list, tuple)):
        return tuple(
            item
            for item in path
            if isinstance(item, Mapping)
            or (not isinstance(item, str) and hasattr(item, "__getitem__"))
        )
    if isinstance(path, Mapping):
        nodes = path.get("nodes")
    else:
        nodes = getattr(path, "nodes", None)
    if not isinstance(nodes, (list, tuple)):
        raise GatewayError("path does not contain a node sequence")
    return tuple(nodes)


def _node_id(node: object) -> int:
    value = _node_value(node, "id")
    if type(value) is not int:
        raise GatewayError("path node id must be an integer")
    return value


def _node_path_key(node: object) -> str:
    value = _node_value(node, "path_key")
    if not isinstance(value, str):
        raise GatewayError("path node path_key must be a string")
    return value


def _node_value(node: object, key: str) -> object:
    if isinstance(node, Mapping):
        return node.get(key)
    try:
        return node[key]  # type: ignore[index]
    except Exception as exc:
        raise GatewayError(f"path node lacks {key}") from exc


def _finite_float(value: object, name: str) -> float:
    if type(value) is int:
        rendered = float(value)
    elif type(value) is float:
        rendered = value
    else:
        raise GatewayError(f"{name} must be numeric")
    if not math.isfinite(rendered):
        raise GatewayError(f"{name} must be finite")
    return rendered


def _normalize_pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


__all__ = ["GatewayError", "HydraGateway"]
