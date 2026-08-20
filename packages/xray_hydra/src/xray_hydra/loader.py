from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Protocol

import polars as pl
from xray_core.models import LoadReport, QuerySpec, Scalar, SnapshotManifest, WriteBatchSpec

from .cypher import RELATION_TYPES, cypher_string_literal, edge_upsert_batch, node_upsert_batch
from .gateway import HydraGateway

logger = logging.getLogger(__name__)


class CheckpointStore(Protocol):
    def get(self, snapshot_id: str, batch_name: str, batch_index: int) -> str | None: ...

    def put(self, snapshot_id: str, batch_name: str, batch_index: int, row_sha256: str) -> None: ...


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str, int], str] = {}

    def get(self, snapshot_id: str, batch_name: str, batch_index: int) -> str | None:
        return self._rows.get((snapshot_id, batch_name, batch_index))

    def put(self, snapshot_id: str, batch_name: str, batch_index: int, row_sha256: str) -> None:
        self._rows[(snapshot_id, batch_name, batch_index)] = row_sha256


class LoaderError(ValueError):
    """Raised when staged snapshot data cannot be safely loaded."""


class HydraLoader:
    def __init__(
        self,
        gateway: HydraGateway,
        *,
        checkpoint_store: CheckpointStore | None = None,
    ) -> None:
        self.gateway = gateway
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()

    def load(
        self,
        snapshot_dir: Path,
        manifest: SnapshotManifest,
        *,
        batch_size: int = 500,
    ) -> LoadReport:
        if batch_size <= 0:
            raise LoaderError("batch_size must be positive")
        resolved_dir = snapshot_dir.resolve()
        self._verify_snapshot_files(resolved_dir, manifest)

        node_rows = _read_node_rows(resolved_dir / "nodes.parquet", manifest.dataset_id)
        node_labels = {int(row["id"]): str(row["label"]) for row in node_rows}
        edge_rows = _read_edge_rows(
            resolved_dir / "edges.parquet", manifest.dataset_id, node_labels
        )
        batches = (
            *_node_batches(node_rows, batch_size),
            *_edge_batches(edge_rows, batch_size),
        )

        completed = 0
        resumed = 0
        failed: list[str] = []
        for index, batch in enumerate(batches):
            row_hash = _batch_hash(batch)
            existing = self.checkpoint_store.get(manifest.snapshot_id, batch.name, index)
            if existing is not None:
                if existing != row_hash:
                    raise LoaderError(f"checkpoint mismatch for {batch.name}[{index}]")
                resumed += 1
                completed += 1
                continue
            try:
                self.gateway.run_batch(batch)
            except Exception as exc:
                logger.exception("HydraDB batch %s[%d] failed", batch.name, index)
                failed.append(f"{batch.name}[{index}]: {type(exc).__name__}: {exc}")
                continue
            self.checkpoint_store.put(manifest.snapshot_id, batch.name, index, row_hash)
            completed += 1

        dataset_literal = cypher_string_literal(manifest.dataset_id)
        verification_queries = (
            QuerySpec(
                name="verify_snapshot_nodes",
                statement=f"MATCH (n {{dataset_id: {dataset_literal}}}) RETURN count(*) AS count",
                parameters={},
                max_len=None,
                result_limit=1,
            ),
            *(
                QuerySpec(
                    name=f"verify_snapshot_edges_{rel_type.lower()}",
                    statement=(
                        f"MATCH (s)-[r:{rel_type} {{dataset_id: {dataset_literal}}}]->(t) "
                        "RETURN count(*) AS count"
                    ),
                    parameters={},
                    max_len=None,
                    result_limit=1,
                )
                for rel_type in sorted(RELATION_TYPES)
            ),
        )
        verified_node_count: int | None = None
        verified_edge_count = 0
        if not failed:
            for query in verification_queries:
                rows = self.gateway.run(query)
                count = _single_count(rows)
                if query.name == "verify_snapshot_nodes":
                    verified_node_count = count
                else:
                    verified_edge_count += count
            expected_nodes = manifest.row_counts["nodes"]
            expected_edges = manifest.row_counts["edges"]
            if verified_node_count != expected_nodes:
                raise LoaderError(
                    f"HydraDB node count mismatch: expected {expected_nodes}, got {verified_node_count}"
                )
            if verified_edge_count != expected_edges:
                raise LoaderError(
                    f"HydraDB edge count mismatch: expected {expected_edges}, got {verified_edge_count}"
                )
        else:
            for query in verification_queries:
                self.gateway.run(query)

        return LoadReport(
            snapshot_id=manifest.snapshot_id,
            node_count=manifest.row_counts["nodes"],
            edge_count=manifest.row_counts["edges"],
            attempted_batches=len(batches),
            completed_batches=completed,
            resumed_batches=resumed,
            failed_batches=tuple(failed),
            graph_fingerprint=_graph_fingerprint(node_rows, edge_rows),
            verification_queries=verification_queries,
        )

    @staticmethod
    def _verify_snapshot_files(snapshot_dir: Path, manifest: SnapshotManifest) -> None:
        for name, expected_digest in manifest.file_sha256.items():
            path = (snapshot_dir / name).resolve()
            if not path.is_relative_to(snapshot_dir):
                raise LoaderError(f"snapshot file escapes snapshot_dir: {name}")
            if not path.exists():
                raise LoaderError(f"snapshot file is missing: {name}")
            actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_digest != expected_digest:
                raise LoaderError(f"snapshot file hash mismatch: {name}")


def _single_count(rows: list[dict[str, object]]) -> int:
    if not rows:
        raise LoaderError("verification query returned no rows")
    value = rows[0].get("count")
    if type(value) is not int:
        raise LoaderError("verification query did not return an integer count")
    return value


def _read_node_rows(path: Path, dataset_id: str) -> tuple[dict[str, Scalar], ...]:
    rows: list[dict[str, Scalar]] = []
    for row in pl.read_parquet(path).to_dicts():
        properties = _properties(row)
        properties["evidence_class"] = _required_str(row, "evidence_class")
        properties["confidence"] = _required_int(row, "confidence")
        rows.append(
            {
                "id": _required_int(row, "id"),
                "canonical_key": _required_str(row, "canonical_key"),
                "path_key": _required_str(row, "path_key"),
                "dataset_id": dataset_id,
                "label": _required_str(row, "label"),
                "properties": json.dumps(properties, sort_keys=True, separators=(",", ":")),
            }
        )
    return tuple(rows)


def _read_edge_rows(
    path: Path, dataset_id: str, node_labels: dict[int, str]
) -> tuple[dict[str, Scalar], ...]:
    rows: list[dict[str, Scalar]] = []
    for row in pl.read_parquet(path).to_dicts():
        properties = _properties(row)
        properties["evidence_class"] = _required_str(row, "evidence_class")
        properties["confidence"] = _required_int(row, "confidence")
        source_id = _required_int(row, "source_id")
        target_id = _required_int(row, "target_id")
        if source_id not in node_labels or target_id not in node_labels:
            raise LoaderError("edge endpoint id is missing from node rows")
        rows.append(
            {
                "id": _required_int(row, "id"),
                "source_id": source_id,
                "target_id": target_id,
                "source_label": node_labels[source_id],
                "target_label": node_labels[target_id],
                "canonical_key": _required_str(row, "canonical_key"),
                "dataset_id": dataset_id,
                "rel_type": _required_str(row, "rel_type"),
                "properties": json.dumps(properties, sort_keys=True, separators=(",", ":")),
            }
        )
    return tuple(rows)


def _node_batches(
    rows: tuple[dict[str, Scalar], ...], batch_size: int
) -> tuple[WriteBatchSpec, ...]:
    by_label: dict[str, list[dict[str, Scalar]]] = defaultdict(list)
    for row in rows:
        by_label[str(row["label"])].append(
            {key: value for key, value in row.items() if key != "label"}
        )
    return tuple(
        node_upsert_batch(label, batch)
        for label in sorted(by_label)
        for batch in _chunks(tuple(by_label[label]), batch_size)
    )


def _edge_batches(
    rows: tuple[dict[str, Scalar], ...], batch_size: int
) -> tuple[WriteBatchSpec, ...]:
    by_shape: dict[tuple[str, str, str], list[dict[str, Scalar]]] = defaultdict(list)
    for row in rows:
        shape = (str(row["rel_type"]), str(row["source_label"]), str(row["target_label"]))
        by_shape[shape].append(
            {
                key: value
                for key, value in row.items()
                if key not in {"rel_type", "source_label", "target_label"}
            }
        )
    return tuple(
        edge_upsert_batch(rel_type, batch, source_label=source_label, target_label=target_label)
        for rel_type, source_label, target_label in sorted(by_shape)
        for batch in _chunks(tuple(by_shape[(rel_type, source_label, target_label)]), batch_size)
    )


def _chunks(
    rows: tuple[dict[str, Scalar], ...],
    batch_size: int,
) -> tuple[tuple[dict[str, Scalar], ...], ...]:
    return tuple(rows[index : index + batch_size] for index in range(0, len(rows), batch_size))


def _properties(row: dict[str, object]) -> dict[str, Scalar]:
    value = row.get("properties_json")
    if not isinstance(value, str):
        raise LoaderError("properties_json must be a string")
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise LoaderError("properties_json must contain an object")
    properties: dict[str, Scalar] = {}
    for key, item in parsed.items():
        if not isinstance(key, str) or type(item) not in {int, float, bool, str}:
            raise LoaderError("properties_json contains an unsupported property")
        properties[key] = item
    return properties


def _required_int(row: dict[str, object], key: str) -> int:
    value = row.get(key)
    if type(value) is not int:
        raise LoaderError(f"{key} must be an integer")
    return value


def _required_str(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise LoaderError(f"{key} must be a non-empty string")
    return value


def _batch_hash(batch: WriteBatchSpec) -> str:
    payload = json.dumps(batch.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _graph_fingerprint(
    nodes: tuple[dict[str, Scalar], ...],
    edges: tuple[dict[str, Scalar], ...],
) -> str:
    payload = json.dumps({"edges": edges, "nodes": nodes}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = ["HydraLoader", "InMemoryCheckpointStore", "LoaderError"]
