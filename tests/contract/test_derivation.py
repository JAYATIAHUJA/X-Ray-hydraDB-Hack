from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_ingest.canonicalize import canonicalize
from xray_ingest.derive import derive_edges
from xray_ingest.gaps import detect_gaps
from xray_ingest.manifest import write_snapshot
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


def test_derived_edges_materialize_fixture_topology_without_cochange_dependency() -> None:
    base = canonicalize(source_records(), "xray-demo-v1")
    edges = derive_edges(base)

    assert Counter(edge.rel_type for edge in edges) == {
        "COMMUNICATES": 12,
        "DEPENDS_ON": 1,
        "OWNS": 3,
    }
    communication = next(
        edge for edge in edges if edge.canonical_key == "communicates:maya-chen:omar-haddad:aggregate"
    )
    assert communication.properties["mention_weight"] == 5
    assert communication.properties["reply_weight"] == 0
    dependency = next(edge for edge in edges if edge.rel_type == "DEPENDS_ON")
    assert dependency.canonical_key == "depends_on:payments-api:ledger-worker:import"
    assert dependency.properties == {"dependency_kind": "import", "weight": 12}
    assert not any("identity-api:audit-sink" in edge.canonical_key for edge in edges)


def test_gap_requires_an_explicit_source_contract() -> None:
    base = canonicalize(source_records(), "xray-demo-v1")

    contracted = detect_gaps(base, sequence_contracts())
    uncontracted = detect_gaps(base, SequenceContractSet())

    assert [node.canonical_key for node in contracted.phantoms] == [
        "artifact:missing-approval"
    ]
    assert uncontracted.phantoms == ()
    assert uncontracted.edges == ()
    assert Counter(edge.rel_type for edge in contracted.edges) == {"PRECEDED_BY": 2}
    assert {
        edge.canonical_key for edge in contracted.edges
    } == {
        "preceded_by:code-change:missing-approval:approval-sequence:v1",
        "preceded_by:missing-approval:directive:approval-sequence:v1",
    }


def test_build_bundle_matches_labelled_fixture_contracts() -> None:
    bundle = build_bundle(source_records(), sequence_contracts(), "xray-demo-v1")
    truth = json.loads((FIXTURE_ROOT / "ground_truth.json").read_text(encoding="utf-8"))

    assert len(bundle.nodes) == 17
    assert len(bundle.edges) == 29
    assert len(bundle.evidence) == 34
    assert truth["ghost_person_key"] in {node.canonical_key for node in bundle.nodes}
    assert truth["gap_path"]["phantom_key"] in {node.canonical_key for node in bundle.nodes}
    assert Counter(edge.rel_type for edge in bundle.edges) == {
        "ABOUT": 2,
        "AUTHORED": 2,
        "COMMUNICATES": 12,
        "DEPENDS_ON": 1,
        "OWNS": 3,
        "PRECEDED_BY": 2,
        "REPORTS_TO": 7,
    }
    assert "Export filtering is an alternative explanation." in bundle.limitations
    assert "Absence does not establish deletion. The corpus is structurally incomplete at this point." in bundle.limitations


def test_snapshot_hash_is_reproducible(tmp_path: Path) -> None:
    bundle = build_bundle(source_records(), sequence_contracts(), "xray-demo-v1")

    first = write_snapshot(bundle, tmp_path / "one")
    second = write_snapshot(bundle, tmp_path / "two")

    assert first.content_sha256 == second.content_sha256
    assert first.row_counts == second.row_counts
    assert "limitations.json" in first.file_sha256
