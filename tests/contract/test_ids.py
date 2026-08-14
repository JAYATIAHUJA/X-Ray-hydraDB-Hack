from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from xray_core.models import CanonicalRecord, EvidenceClass
from xray_ingest.canonicalize import CanonicalizationError, canonicalize
from xray_ingest.ids import IdCollisionError, IdRegistry, path_key, stable_id

FIXTURE_ROOT = Path(__file__).parents[2] / "data" / "fixtures" / "xray-demo"
ASCII_IDENTITY = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=1,
    max_size=64,
)


def source_records() -> tuple[CanonicalRecord, ...]:
    records: list[CanonicalRecord] = []
    for name in ("directory.json", "events.json", "git_facts.json"):
        payloads = json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
        records.extend(CanonicalRecord.model_validate(payload) for payload in payloads)
    return tuple(records)


@given(dataset_id=ASCII_IDENTITY, label=ASCII_IDENTITY, canonical_key=ASCII_IDENTITY)
def test_stable_id_is_deterministic_positive_signed_63_bit(
    dataset_id: str,
    label: str,
    canonical_key: str,
) -> None:
    first = stable_id(dataset_id, label, canonical_key)
    second = stable_id(dataset_id, label, canonical_key)

    assert first == second
    assert 1 <= first <= 2**63 - 1


def test_stable_id_matches_the_published_demo_identity() -> None:
    assert stable_id("xray-demo-v1", "Person", "person:maya-chen") == 8735786581004019202


def test_stable_id_remaps_an_all_zero_digest_to_one(monkeypatch: pytest.MonkeyPatch) -> None:
    class ZeroDigest:
        @staticmethod
        def digest() -> bytes:
            return b"\x00" * 8

    monkeypatch.setattr("xray_ingest.ids.hashlib.blake2b", lambda *_args, **_kwargs: ZeroDigest())

    assert stable_id("dataset", "Person", "person:test") == 1


def test_path_key_accepts_signed_63_bit_boundaries_and_rejects_reserved_zero() -> None:
    assert path_key("Person", 1) == "person:00000000000000000001"
    assert path_key("Module", 2**63 - 1) == "module:09223372036854775807"

    with pytest.raises(ValueError, match="positive signed 63-bit"):
        path_key("Person", 0)
    with pytest.raises(ValueError, match="positive signed 63-bit"):
        path_key("Person", 2**63)
    with pytest.raises(ValueError, match="positive signed 63-bit"):
        path_key("Person", True)
    with pytest.raises(ValueError, match="ASCII letters"):
        path_key("Person Node", 1)


def test_registry_fails_closed_on_an_injected_hash_collision() -> None:
    registry = IdRegistry(id_factory=lambda _dataset, _label, _key: 7)
    assert registry.register("dataset", "Person", "person:first") == 7
    assert registry.register("dataset", "Person", "person:first") == 7

    with pytest.raises(IdCollisionError, match="collision"):
        registry.register("dataset", "Person", "person:second")


def test_canonicalize_registers_generated_identities() -> None:
    with pytest.raises(IdCollisionError, match="collision"):
        canonicalize(
            source_records(),
            "xray-demo-v1",
            id_factory=lambda _dataset, _label, _key: 7,
        )


def test_canonicalize_registers_edge_identities() -> None:
    def collide_relationships(dataset_id: str, label: str, canonical_key: str) -> int:
        if label.isupper():
            return 7
        return stable_id(dataset_id, label, canonical_key)

    with pytest.raises(IdCollisionError, match="collision"):
        canonicalize(
            source_records(),
            "xray-demo-v1",
            id_factory=collide_relationships,
        )


def test_canonicalization_is_order_independent() -> None:
    records = source_records()
    first = canonicalize(records, "xray-demo-v1").model_dump_json()
    second = canonicalize(reversed(records), "xray-demo-v1").model_dump_json()

    assert first == second


def test_canonicalization_ignores_metadata_insertion_order() -> None:
    records = source_records()
    first = records[0]
    reordered = first.model_copy(update={"metadata": dict(reversed(first.metadata.items()))})
    reordered_records = (reordered, *records[1:])

    assert canonicalize(reordered_records, "xray-demo-v1") == canonicalize(records, "xray-demo-v1")


def test_canonicalization_is_idempotent_for_exact_duplicate_records() -> None:
    records = source_records()
    original = canonicalize(records, "xray-demo-v1")
    duplicated = canonicalize((*records, *records), "xray-demo-v1")

    assert duplicated == original


def test_canonicalization_merges_compatible_multi_source_provenance() -> None:
    records = source_records()
    alex = next(record for record in records if record.external_id == "alex-rivera")
    priya = next(record for record in records if record.external_id == "priya-shah")
    corroborating_priya = priya.model_copy(update={"source": "corroborating-directory"})

    bundle = canonicalize((alex, priya, corroborating_priya), "multi-source")

    assert len(bundle.nodes) == 2
    assert len(bundle.edges) == 1
    merged_priya = next(node for node in bundle.nodes if node.canonical_key == "person:priya-shah")
    assert len(merged_priya.evidence_ids) == 2
    assert len(bundle.edges[0].evidence_ids) == 2


def test_artifact_about_edges_cover_every_module_subject_and_canonical_alias() -> None:
    records = source_records()
    alex = next(record for record in records if record.external_id == "alex-rivera")
    modules = tuple(record for record in records if record.kind == "module")[:2]
    directive = next(record for record in records if record.external_id == "directive")
    multi_module_artifact = directive.model_copy(
        update={
            "external_id": "multi-module",
            "subjects": (
                "artifact:source-alias",
                "module:payments-api",
                "module:ledger-worker",
            ),
            "metadata": {
                **directive.metadata,
                "canonical_key": "artifact:multi-module",
            },
        }
    )

    bundle = canonicalize((alex, *modules, multi_module_artifact), "multi-module")

    assert Counter(edge.rel_type for edge in bundle.edges) == {"ABOUT": 2, "AUTHORED": 1}
    assert {edge.canonical_key for edge in bundle.edges if edge.rel_type == "ABOUT"} == {
        "about:multi-module:ledger-worker",
        "about:multi-module:payments-api",
    }


def test_canonicalization_never_upgrades_inferred_source_claims_to_observed() -> None:
    records = source_records()
    alex = next(record for record in records if record.external_id == "alex-rivera")
    payments = next(record for record in records if record.external_id == "module-payments-api")
    directive = next(record for record in records if record.external_id == "directive")
    inferred_artifact = directive.model_copy(
        update={"metadata": {**directive.metadata, "evidence_class": "inferred"}}
    )

    bundle = canonicalize((alex, payments, inferred_artifact), "inferred-artifact")

    artifact = next(node for node in bundle.nodes if node.label == "Artifact")
    assert artifact.evidence_class is EvidenceClass.INFERRED
    assert {edge.evidence_class for edge in bundle.edges} == {EvidenceClass.INFERRED}


def test_canonicalization_rejects_conflicting_source_record_identity() -> None:
    first = source_records()[0]
    conflicting = first.model_copy(update={"metadata": {**first.metadata, "role_rank": 99}})

    with pytest.raises(CanonicalizationError, match="Conflicting source record"):
        canonicalize((first, conflicting), "xray-demo-v1")


def test_demo_canonicalization_materializes_safe_observed_topology() -> None:
    bundle = canonicalize(source_records(), "xray-demo-v1")

    assert len(bundle.nodes) == 16
    assert len(bundle.edges) == 11
    assert len(bundle.evidence) == 33
    assert len({node.id for node in bundle.nodes}) == len(bundle.nodes)
    assert len({node.path_key for node in bundle.nodes}) == len(bundle.nodes)
    maya = next(node for node in bundle.nodes if node.canonical_key == "person:maya-chen")
    assert maya.id == 8735786581004019202
    assert maya.path_key == "person:08735786581004019202"
    assert maya.properties["role_rank"] == 1
    assert "manager_external_id" not in maya.properties
    assert "title" not in maya.properties
    dependency_evidence = next(
        record for record in bundle.evidence if record.predicate == "dependency"
    )
    dependency_metadata = json.loads(dependency_evidence.metadata_json)["metadata"]
    assert dependency_metadata["dependency_kind"] == "import"
    assert dependency_metadata["weight"] == 12
    coupling_evidence = next(record for record in bundle.evidence if record.predicate == "cochange")
    assert coupling_evidence.evidence_class is EvidenceClass.INFERRED
    assert Counter(edge.rel_type for edge in bundle.edges) == {
        "ABOUT": 2,
        "AUTHORED": 2,
        "REPORTS_TO": 7,
    }
    assert not {"COMMUNICATES", "OWNS", "DEPENDS_ON", "PRECEDED_BY"} & {
        edge.rel_type for edge in bundle.edges
    }
    assert [node.id for node in bundle.nodes] == sorted(node.id for node in bundle.nodes)
    assert [edge.id for edge in bundle.edges] == sorted(edge.id for edge in bundle.edges)
    assert [record.evidence_id for record in bundle.evidence] == sorted(
        record.evidence_id for record in bundle.evidence
    )
    assert Counter(record.predicate for record in bundle.evidence) == {
        "artifact": 2,
        "authorship_aggregate": 3,
        "cochange": 1,
        "communication_aggregate": 12,
        "dependency": 1,
        "directory_person": 10,
        "module": 4,
    }
    node_ids = {node.id for node in bundle.nodes}
    assert all(edge.source_id in node_ids and edge.target_id in node_ids for edge in bundle.edges)


def test_canonicalize_consumes_any_iterable_once() -> None:
    def record_stream() -> Iterable[CanonicalRecord]:
        yield from source_records()

    assert canonicalize(record_stream(), "xray-demo-v1") == canonicalize(
        source_records(), "xray-demo-v1"
    )
