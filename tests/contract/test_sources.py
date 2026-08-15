from __future__ import annotations

from xray_analytics import gap_findings
from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_ingest.canonicalize import canonicalize
from xray_ingest.derive import derive_edges
from xray_ingest.gaps import detect_gaps
from xray_ingest.sources import (
    SourceAdapterError,
    code_records,
    email_records,
    slack_records,
    ticket_records,
)


def test_source_adapters_normalize_explicit_source_facts_without_text_inference() -> None:
    records = (
        *slack_records(
            [
                {
                    "id": "171234.0001",
                    "occurred_at_epoch": 1712340001,
                    "author_id": "maya",
                    "text": "Can you review this?",
                    "parent_author_id": "alex",
                    "mentions": ["priya"],
                    "module_keys": ["payments-api"],
                }
            ]
        ),
        *email_records(
            [
                {
                    "id": "message-1",
                    "occurred_at_epoch": 1712340010,
                    "from_id": "alex",
                    "to_ids": ["maya"],
                    "subject": "Payments rollout",
                    "module_keys": ["payments-api"],
                }
            ]
        ),
        *ticket_records(
            [
                {
                    "id": "PAY-123",
                    "occurred_at_epoch": 1712340020,
                    "reporter_id": "priya",
                    "title": "Retry issue",
                    "module_keys": ["payments-api"],
                }
            ]
        ),
        *code_records(
            [
                {
                    "sha": "abc123",
                    "occurred_at_epoch": 1712340030,
                    "author_id": "alex",
                    "message": "Add retry",
                    "module_keys": ["payments-api"],
                }
            ]
        ),
    )

    assert len(records) == 7
    assert records[0].metadata["canonical_key"] == "artifact:slack:171234.0001"
    assert {
        record.metadata["interaction_kind"]
        for record in records
        if record.kind == "communication_aggregate"
    } == {
        "email",
        "mention",
        "reply",
    }


def test_email_relationship_is_derived_as_communication_weight() -> None:
    people = tuple(
        {
            "source": "directory",
            "external_id": person,
            "kind": "directory_person",
            "occurred_at_epoch": 1,
            "author_external_id": None,
            "parent_external_id": None,
            "subjects": [f"person:{person}"],
            "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "content": None,
            "metadata": {},
        }
        for person in ("alex", "maya")
    )
    bundle = canonicalize(
        (
            *tuple(CanonicalRecord.model_validate(person) for person in people),
            *email_records(
                [
                    {
                        "id": "message-1",
                        "occurred_at_epoch": 2,
                        "from_id": "alex",
                        "to_ids": ["maya"],
                    }
                ]
            ),
        ),
        "source-adapter-test",
    )
    edge = next(edge for edge in derive_edges(bundle) if edge.rel_type == "COMMUNICATES")
    assert edge.properties["email_weight"] == 1
    assert edge.properties["weight"] == 1


def test_source_adapters_require_explicit_ids_and_module_lists() -> None:
    try:
        slack_records(
            [{"id": "message", "occurred_at_epoch": 1, "author_id": "maya", "mentions": "alex"}]
        )
    except SourceAdapterError as error:
        assert "mentions" in str(error)
    else:
        raise AssertionError("expected a source adapter validation error")


def _person_record(person: str) -> CanonicalRecord:
    return CanonicalRecord.model_validate(
        {
            "source": "directory",
            "external_id": person,
            "kind": "directory_person",
            "occurred_at_epoch": 1,
            "author_external_id": None,
            "parent_external_id": None,
            "subjects": [f"person:{person}"],
            "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "content": None,
            "metadata": {},
        }
    )


def test_known_thread_parent_becomes_replies_to_edge() -> None:
    records = (
        _person_record("alex"),
        _person_record("maya"),
        *slack_records(
            [
                {"id": "parent", "occurred_at_epoch": 2, "author_id": "alex"},
                {
                    "id": "child",
                    "occurred_at_epoch": 3,
                    "author_id": "maya",
                    "thread_parent_id": "parent",
                },
            ]
        ),
    )
    bundle = canonicalize(records, "thread-test")

    reply = next(edge for edge in bundle.edges if edge.rel_type == "REPLIES_TO")
    assert reply.canonical_key == "replies_to:slack:child:slack:parent"


def test_dangling_thread_parent_becomes_phantom_and_reply_edge() -> None:
    records = (
        _person_record("maya"),
        *slack_records(
            [
                {
                    "id": "child",
                    "occurred_at_epoch": 3,
                    "author_id": "maya",
                    "thread_parent_id": "deleted-parent",
                }
            ]
        ),
    )
    base = canonicalize(records, "dangling-thread-test")
    gaps = detect_gaps(base, SequenceContractSet())

    assert [node.canonical_key for node in gaps.phantoms] == ["artifact:slack:deleted-parent"]
    assert gaps.phantoms[0].properties["reason"] == "dangling_thread_parent"
    assert [edge.rel_type for edge in gaps.edges] == ["REPLIES_TO"]
    assert "absence does not establish deletion" in " ".join(gaps.limitations)

    derived = detect_gaps(base, SequenceContractSet())
    enriched = base.model_copy(
        update={
            "nodes": (*base.nodes, *derived.phantoms),
            "edges": (*base.edges, *derived.edges),
        }
    )
    finding = gap_findings(enriched)[0]
    assert finding.reason == "dangling_thread_parent"
    assert finding.successor_keys == ("artifact:slack:child",)
