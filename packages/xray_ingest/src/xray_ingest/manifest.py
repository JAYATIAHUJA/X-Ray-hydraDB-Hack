from __future__ import annotations

import hashlib
import json
from pathlib import Path

import polars as pl
from xray_core.jsonutil import canonical_json
from xray_core.models import CanonicalBundle, EdgeRow, EvidenceRecord, NodeRow, SnapshotManifest


def _write_json(path: Path, value: object) -> None:
    path.write_text(f"{canonical_json(value)}\n", encoding="utf-8", newline="\n")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_content_hash(file_sha256: dict[str, str], row_counts: dict[str, int]) -> str:
    payload = canonical_json({"file_sha256": file_sha256, "row_counts": row_counts})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    pl.DataFrame(rows).write_parquet(path)


def _node_rows(bundle: CanonicalBundle) -> list[dict[str, object]]:
    return [
        {
            "id": node.id,
            "canonical_key": node.canonical_key,
            "path_key": node.path_key,
            "label": node.label,
            "evidence_class": node.evidence_class.value,
            "confidence": node.confidence,
            "properties_json": canonical_json(node.properties),
        }
        for node in bundle.nodes
    ]


def _edge_rows(bundle: CanonicalBundle) -> list[dict[str, object]]:
    return [
        {
            "id": edge.id,
            "canonical_key": edge.canonical_key,
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "rel_type": edge.rel_type,
            "evidence_class": edge.evidence_class.value,
            "confidence": edge.confidence,
            "properties_json": canonical_json(edge.properties),
        }
        for edge in bundle.edges
    ]


def _evidence_rows(bundle: CanonicalBundle) -> list[dict[str, object]]:
    return [
        record.model_dump(mode="json")
        for record in sorted(bundle.evidence, key=lambda evidence: evidence.evidence_id)
    ]


def _node_evidence_rows(bundle: CanonicalBundle) -> list[dict[str, object]]:
    return [
        {"node_id": node.id, "evidence_id": evidence_id}
        for node in bundle.nodes
        for evidence_id in node.evidence_ids
    ]


def _edge_evidence_rows(bundle: CanonicalBundle) -> list[dict[str, object]]:
    return [
        {"edge_id": edge.id, "evidence_id": evidence_id}
        for edge in bundle.edges
        for evidence_id in edge.evidence_ids
    ]


def write_snapshot(bundle: CanonicalBundle, root: Path) -> SnapshotManifest:
    root.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, list[dict[str, object]]] = {
        "nodes.parquet": _node_rows(bundle),
        "edges.parquet": _edge_rows(bundle),
        "evidence.parquet": _evidence_rows(bundle),
        "node_evidence.parquet": _node_evidence_rows(bundle),
        "edge_evidence.parquet": _edge_evidence_rows(bundle),
    }
    for name, rows in artifacts.items():
        _write_parquet(root / name, rows)
    _write_json(root / "limitations.json", {"limitations": bundle.limitations})

    row_counts = {
        "nodes": len(bundle.nodes),
        "edges": len(bundle.edges),
        "evidence": len(bundle.evidence),
        "node_evidence": sum(len(node.evidence_ids) for node in bundle.nodes),
        "edge_evidence": sum(len(edge.evidence_ids) for edge in bundle.edges),
        "limitations": len(bundle.limitations),
    }
    file_sha256 = {
        name: _sha256_file(root / name)
        for name in (
            "nodes.parquet",
            "edges.parquet",
            "evidence.parquet",
            "node_evidence.parquet",
            "edge_evidence.parquet",
            "limitations.json",
        )
    }
    content_sha256 = _snapshot_content_hash(file_sha256, row_counts)
    manifest = SnapshotManifest(
        snapshot_id=f"{bundle.dataset_id}:{content_sha256[:16]}",
        dataset_id=bundle.dataset_id,
        schema_version="1.0.0",
        content_sha256=content_sha256,
        row_counts=row_counts,
        file_sha256=file_sha256,
    )
    _write_json(root / "manifest.json", manifest.model_dump(mode="json"))
    return manifest


class ParquetEvidenceRepository:
    def __init__(self, snapshot_dir: Path) -> None:
        self.snapshot_dir = snapshot_dir
        evidence_path = snapshot_dir / "evidence.parquet"
        if not evidence_path.exists():
            raise FileNotFoundError(evidence_path)
        self._evidence = tuple(
            EvidenceRecord.model_validate(row) for row in pl.read_parquet(evidence_path).to_dicts()
        )
        self._by_id = {record.evidence_id: record for record in self._evidence}

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        return self._by_id.get(evidence_id)

    def list(self) -> tuple[EvidenceRecord, ...]:
        return self._evidence

    def limitations(self) -> tuple[str, ...]:
        path = self.snapshot_dir / "limitations.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        limitations = payload.get("limitations")
        if not isinstance(limitations, list) or not all(
            isinstance(item, str) for item in limitations
        ):
            raise ValueError("limitations.json is malformed")
        return tuple(limitations)


def read_snapshot(root: Path, *, verify: bool = True) -> CanonicalBundle:
    """Load a snapshot directory written by ``write_snapshot`` back into a bundle.

    With ``verify`` the manifest's per-file SHA-256 digests are checked first, so a
    partially written or edited snapshot is rejected rather than silently served.
    """
    manifest_path = root / "manifest.json"
    manifest = SnapshotManifest.model_validate(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    if verify:
        for name, expected in manifest.file_sha256.items():
            actual = _sha256_file(root / name)
            if actual != expected:
                raise ValueError(f"snapshot file hash mismatch: {name}")

    node_evidence: dict[int, list[str]] = {}
    for row in pl.read_parquet(root / "node_evidence.parquet").to_dicts():
        node_evidence.setdefault(int(row["node_id"]), []).append(str(row["evidence_id"]))
    edge_evidence: dict[int, list[str]] = {}
    for row in pl.read_parquet(root / "edge_evidence.parquet").to_dicts():
        edge_evidence.setdefault(int(row["edge_id"]), []).append(str(row["evidence_id"]))

    nodes = tuple(
        NodeRow.model_validate(
            {
                "id": row["id"],
                "canonical_key": row["canonical_key"],
                "path_key": row["path_key"],
                "label": row["label"],
                "evidence_class": row["evidence_class"],
                "confidence": row["confidence"],
                "properties": json.loads(row["properties_json"]),
                "evidence_ids": tuple(node_evidence.get(int(row["id"]), ())),
            }
        )
        for row in pl.read_parquet(root / "nodes.parquet").to_dicts()
    )
    edges = tuple(
        EdgeRow.model_validate(
            {
                "id": row["id"],
                "canonical_key": row["canonical_key"],
                "source_id": row["source_id"],
                "target_id": row["target_id"],
                "rel_type": row["rel_type"],
                "evidence_class": row["evidence_class"],
                "confidence": row["confidence"],
                "properties": json.loads(row["properties_json"]),
                "evidence_ids": tuple(edge_evidence.get(int(row["id"]), ())),
            }
        )
        for row in pl.read_parquet(root / "edges.parquet").to_dicts()
    )
    evidence = tuple(
        EvidenceRecord.model_validate(row)
        for row in pl.read_parquet(root / "evidence.parquet").to_dicts()
    )
    limitations_payload = json.loads((root / "limitations.json").read_text(encoding="utf-8"))
    return CanonicalBundle(
        dataset_id=manifest.dataset_id,
        nodes=nodes,
        edges=edges,
        evidence=evidence,
        limitations=tuple(limitations_payload.get("limitations", ())),
    )


__all__ = ["ParquetEvidenceRepository", "read_snapshot", "write_snapshot"]
