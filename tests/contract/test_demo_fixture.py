from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

FIXTURE_ROOT = Path(__file__).parents[2] / "data" / "fixtures" / "xray-demo"
SCHEMA_ROOT = Path(__file__).parents[2] / "data" / "schemas"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def demo_fixture() -> dict[str, Any]:
    manifest = load_json(FIXTURE_ROOT / "manifest.json")
    manifest["ground_truth"] = load_json(FIXTURE_ROOT / "ground_truth.json")
    return manifest


def test_demo_fixture_declares_three_evidence_backed_findings(
    demo_fixture: dict[str, Any],
) -> None:
    assert demo_fixture["dataset_id"] == "xray-demo-v1"
    assert demo_fixture["ground_truth"] == {
        "ghost_person_key": "person:maya-chen",
        "faultline_module_keys": ["module:payments-api", "module:ledger-worker"],
        "gap_path": {
            "source_artifact_key": "artifact:code-change",
            "target_artifact_key": "artifact:directive",
            "phantom_key": "artifact:missing-approval",
        },
    }
    assert set(demo_fixture["evidence_classes"]) == {
        "observed",
        "inferred",
        "demo_ground_truth",
    }


def test_demo_fixture_sources_match_schema_and_manifest_hashes() -> None:
    manifest = load_json(FIXTURE_ROOT / "manifest.json")
    canonical_schema = load_json(SCHEMA_ROOT / "canonical-record.schema.json")
    canonical_validator = Draft202012Validator(canonical_schema)

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


def test_demo_fixture_encodes_the_required_topology() -> None:
    directory = load_json(FIXTURE_ROOT / "directory.json")
    events = load_json(FIXTURE_ROOT / "events.json")
    git_facts = load_json(FIXTURE_ROOT / "git_facts.json")
    manifest = load_json(FIXTURE_ROOT / "manifest.json")

    assert [record["external_id"] for record in directory] == [
        "maya-chen",
        "alex-rivera",
        "priya-shah",
        "omar-haddad",
        "lena-park",
        "theo-brooks",
        "nina-okafor",
        "sam-wu",
        "ines-costa",
        "jon-bell",
    ]
    maya = next(record for record in directory if record["external_id"] == "maya-chen")
    assert maya["metadata"]["role_rank"] == 1

    communication_records = [
        record for record in events if record["kind"] == "communication_aggregate"
    ]
    communications = [
        (
            record["metadata"]["sender_external_id"],
            record["metadata"]["recipient_external_id"],
            record["metadata"]["interaction_count"],
        )
        for record in communication_records
    ]
    assert communications == [
        ("alex-rivera", "priya-shah", 3),
        ("alex-rivera", "maya-chen", 5),
        ("priya-shah", "maya-chen", 4),
        ("maya-chen", "omar-haddad", 5),
        ("maya-chen", "lena-park", 4),
        ("omar-haddad", "lena-park", 3),
        ("nina-okafor", "sam-wu", 20),
        ("nina-okafor", "ines-costa", 20),
        ("nina-okafor", "jon-bell", 20),
        ("sam-wu", "ines-costa", 1),
        ("sam-wu", "jon-bell", 1),
        ("ines-costa", "jon-bell", 1),
    ]
    weighted_degree: Counter[str] = Counter()
    for source, target, weight in communications:
        weighted_degree[source] += weight
        weighted_degree[target] += weight
    assert weighted_degree.most_common(1) == [("nina-okafor", 60)]
    assert "theo-brooks" not in weighted_degree

    dependency = next(record for record in git_facts if record["kind"] == "dependency")
    assert dependency["metadata"] == {
        "dependency_kind": "import",
        "source_module_external_id": "payments-api",
        "target_module_external_id": "ledger-worker",
        "weight": 12,
    }
    coupling = next(record for record in git_facts if record["kind"] == "cochange")
    assert coupling["metadata"]["relationship_class"] == "inferred_coupling"
    assert "dependency_kind" not in coupling["metadata"]

    owners = {
        record["metadata"]["module_external_id"]: record["author_external_id"]
        for record in git_facts
        if record["kind"] == "authorship_aggregate"
    }
    assert owners == {
        "payments-api": "alex-rivera",
        "ledger-worker": "theo-brooks",
        "identity-api": "omar-haddad",
    }

    artifact_keys = {
        record["metadata"]["canonical_key"] for record in events if record["kind"] == "artifact"
    }
    assert artifact_keys == {"artifact:directive", "artifact:code-change"}
    assert "artifact:missing-approval" not in artifact_keys
    assert [step["canonical_key"] for step in manifest["sequence_contracts"][0]["steps"]] == [
        "artifact:directive",
        "artifact:missing-approval",
        "artifact:code-change",
    ]
