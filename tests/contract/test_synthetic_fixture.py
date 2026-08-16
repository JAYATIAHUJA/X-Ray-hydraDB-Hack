from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from xray_analytics.analysis import faultlines, gap_findings
from xray_api.dependencies import SYNTH_DATASET_ID, active_bundle, active_dataset_id, synth_bundle

FIXTURE_ROOT = Path(__file__).parents[2] / "data" / "fixtures" / "xray-synth-500"
SCHEMA_ROOT = Path(__file__).parents[2] / "data" / "schemas"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_synth500_fixture_sources_match_manifest_hashes_and_schema() -> None:
    manifest = load_json(FIXTURE_ROOT / "manifest.json")
    canonical_schema = load_json(SCHEMA_ROOT / "canonical-record.schema.json")
    canonical_validator = Draft202012Validator(canonical_schema)

    assert manifest["dataset_id"] == SYNTH_DATASET_ID
    assert manifest["acceptance_labels"] == {
        "faultline_count": 3,
        "gap_count": 5,
        "ghost_broker_key": "person:p0000",
    }

    for descriptor in manifest["source_files"]:
        source_path = FIXTURE_ROOT / descriptor["path"]
        records = load_json(source_path)
        assert descriptor["input_status"] == "complete"
        assert len(records) == descriptor["record_count"]
        assert hashlib.sha256(source_path.read_bytes()).hexdigest() == descriptor["sha256"]
        for record in records:
            canonical_validator.validate(record)

    ground_truth_path = FIXTURE_ROOT / manifest["ground_truth_file"]
    ground_truth_schema = load_json(SCHEMA_ROOT / "ground-truth.schema.json")
    Draft202012Validator(ground_truth_schema).validate(load_json(ground_truth_path))
    assert (
        hashlib.sha256(ground_truth_path.read_bytes()).hexdigest()
        == manifest["ground_truth_descriptor"]["sha256"]
    )


def test_synth500_ingests_planted_faultlines_and_gaps() -> None:
    bundle = synth_bundle()
    truth = load_json(FIXTURE_ROOT / "ground_truth.json")

    assert bundle.dataset_id == SYNTH_DATASET_ID
    assert sum(1 for node in bundle.nodes if node.label == "Person") == 500
    assert sum(1 for node in bundle.nodes if node.label == "Module") == 40

    observed_faultline_pairs = {
        (finding.source_module_key, finding.target_module_key) for finding in faultlines(bundle)
    }
    planted_faultline_pairs = {tuple(pair) for pair in truth["faultline_module_pairs"]}
    assert planted_faultline_pairs <= observed_faultline_pairs

    observed_gap_keys = {finding.phantom_key for finding in gap_findings(bundle)}
    planted_gap_keys = {path["phantom_key"] for path in truth["gap_paths"]}
    assert observed_gap_keys == planted_gap_keys


def test_synth500_fixture_variant_selects_synthetic_bundle(monkeypatch: Any) -> None:
    monkeypatch.setenv("XRAY_FIXTURE_VARIANT", "synth500")

    assert active_dataset_id() == SYNTH_DATASET_ID
    assert active_bundle().dataset_id == SYNTH_DATASET_ID
