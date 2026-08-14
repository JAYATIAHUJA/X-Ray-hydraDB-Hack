from __future__ import annotations

import json
from pathlib import Path

import pytest
from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_core.ports import EvidenceRepository
from xray_ingest.manifest import ParquetEvidenceRepository, write_snapshot
from xray_ingest.pipeline import build_bundle

FIXTURE_ROOT = Path(__file__).parents[2] / "data" / "fixtures" / "xray-demo"


def source_records() -> tuple[CanonicalRecord, ...]:
    records: list[CanonicalRecord] = []
    for name in ("directory.json", "events.json", "git_facts.json"):
        records.extend(
            CanonicalRecord.model_validate(payload)
            for payload in json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
        )
    return tuple(records)


def sequence_contracts() -> SequenceContractSet:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    return SequenceContractSet.model_validate(
        {
            "contracts": manifest["sequence_contracts"],
            "limitations": manifest["limitations"],
        }
    )


@pytest.mark.integration
def test_parquet_evidence_repository_reopens_snapshot(tmp_path: Path) -> None:
    bundle = build_bundle(source_records(), sequence_contracts(), "xray-demo-v1")
    manifest = write_snapshot(bundle, tmp_path / "snapshot")

    repository: EvidenceRepository = ParquetEvidenceRepository(tmp_path / "snapshot")
    gap_evidence = next(record for record in bundle.evidence if record.predicate == "gap_phantom")

    assert manifest.row_counts["evidence"] == 34
    assert repository.get(gap_evidence.evidence_id) == gap_evidence
    assert len(repository.list()) == 34
    assert "limitations.json" in manifest.file_sha256
    assert "This is a labelled synthetic fixture and is not a measured real-organization result." in repository.limitations()
