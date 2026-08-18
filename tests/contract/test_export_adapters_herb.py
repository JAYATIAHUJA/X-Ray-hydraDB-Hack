"""Contract tests for the Salesforce HERB adapter (official Track 01 corpus).

Fixtures are tiny hand-written HERB-shaped JSON files: the adapter must read explicit
ids only, never infer from prose, and must feed the standard ``ingest_exports``
pipeline unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_ingest.adapters.herb import (
    herb_directory_records,
    herb_document_rows,
    herb_pr_rows,
    herb_role_rank,
    herb_slack_rows,
)
from xray_ingest.pipeline import ingest_exports

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_EMPLOYEES = {
    "eid_aaaaaaaa": {
        "employee_id": "eid_aaaaaaaa",
        "name": "Priya Nair",
        "role": "Software Engineer",
        "location": "Remote",
        "org": "slack",
    },
    "eid_bbbbbbbb": {
        "employee_id": "eid_bbbbbbbb",
        "name": "Marcus Lee",
        "role": "Engineering Lead",
        "location": "Austin",
        "org": "slack",
    },
    "eid_cccccccc": {
        "employee_id": "eid_cccccccc",
        "name": "Hannah Taylor",
        "role": "VP of Engineering",
        "location": "SF",
        "org": "slack",
    },
    "eid_dddddddd": {
        "employee_id": "eid_dddddddd",
        "name": "Ines Roy",
        "role": "Product Manager",
        "location": "Berlin",
        "org": "slack",
    },
}

_TEAM = [
    {
        "employee_id": "eid_cccccccc",
        "name": "Hannah Taylor",
        "role": "VP of Engineering",
        "engineering_leads": [
            {
                "employee_id": "eid_bbbbbbbb",
                "name": "Marcus Lee",
                "role": "Engineering Lead",
                "engineers": [
                    {
                        "employee_id": "eid_aaaaaaaa",
                        "name": "Priya Nair",
                        "role": "Software Engineer",
                    }
                ],
                "qa_specialists": [],
            }
        ],
        "product_managers": [
            {"employee_id": "eid_dddddddd", "name": "Ines Roy", "role": "Product Manager"}
        ],
    }
]

_PRODUCT = {
    "team": ["eid_aaaaaaaa", "eid_bbbbbbbb"],
    "customers": [],
    "slack": [
        {
            "Channel": {"name": "planning-demo", "channelID": "ch-1"},
            "Message": {
                "User": {
                    "userId": "slack_admin_bot",
                    "timestamp": "2026-03-01T09:00:00",
                    "text": "channel created",
                    "utterranceID": "u0",
                },
                "Reactions": [],
            },
            "ThreadReplies": [],
            "id": "u0",
        },
        {
            "Channel": {"name": "planning-demo", "channelID": "ch-1"},
            "Message": {
                "User": {
                    "userId": "eid_aaaaaaaa",
                    "timestamp": "2026-03-01T09:05:00",
                    "text": "@eid_bbbbbbbb can you review? cc @eid_dddddddd — and ignore me @eid_aaaaaaaa",
                    "utterranceID": "u1",
                },
                "Reactions": [],
            },
            "ThreadReplies": [],
            "id": "u1",
        },
        {
            "Channel": {"name": "planning-demo", "channelID": "ch-1"},
            "Message": {
                "User": {
                    "userId": "eid_bbbbbbbb",
                    "timestamp": "not-a-date",
                    "text": "bad stamp",
                    "utterranceID": "u2",
                },
                "Reactions": [],
            },
            "ThreadReplies": [],
            "id": "u2",
        },
    ],
    "documents": [
        {
            "content": "…",
            "date": "2026-02-20T10:00:00",
            "author": "eid_dddddddd",
            "document_link": "x",
            "type": "PRD",
            "id": "prd_1",
        }
    ],
    "meeting_transcripts": [
        {
            "transcript": "…",
            "date": "2026-02-21T10:00:00",
            "participants": "['eid_aaaaaaaa']",
            "id": "m1",
        }
    ],
    "meeting_chats": [],
    "urls": [],
    "prs": [
        {
            "title": "Add thing",
            "summary": "…",
            "link": "https://github.com/x/y/pull/1",
            "number": "1",
            "state": "closed",
            "user": {"login": "eid_aaaaaaaa"},
            "created_at": "2026-03-02T00:00:00",
            "reviews": [
                {
                    "state": "APPROVED",
                    "user": {"login": "eid_bbbbbbbb"},
                    "comment": "LGTM",
                    "submitted_at": "2026-03-02T01:00:00",
                },
                {
                    "state": "COMMENTED",
                    "user": {"login": "EMP_123"},
                    "comment": "nit",
                    "submitted_at": "",
                },
            ],
            "id": "pr_1",
        }
    ],
    "answerable_questions": [],
    "unanswerable_questions": [],
}


def _write(tmp: Path) -> tuple[Path, Path, Path]:
    emp = tmp / "employee.json"
    team = tmp / "salesforce_team.json"
    prod = tmp / "DemoForce.json"
    emp.write_text(json.dumps(_EMPLOYEES), encoding="utf-8")
    team.write_text(json.dumps(_TEAM), encoding="utf-8")
    prod.write_text(json.dumps(_PRODUCT), encoding="utf-8")
    return emp, team, prod


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_role_rank_follows_spec_scale() -> None:
    assert herb_role_rank("VP of Engineering") == 6
    assert herb_role_rank("Chief Product Officer") == 6
    assert herb_role_rank("Engineering Lead") == 3
    assert herb_role_rank("Software Engineer") == 1
    assert herb_role_rank("QA Specialist") == 1
    assert herb_role_rank("Something Unknown") == 0


def test_directory_records_carry_rank_and_team(tmp_path: Path) -> None:
    emp, team, _ = _write(tmp_path)
    records = herb_directory_records(emp, team, ["DemoForce"])
    people = {r["external_id"]: r for r in records if r["kind"] == "directory_person"}
    modules = [r for r in records if r["kind"] == "module"]

    assert set(people) == set(_EMPLOYEES)
    assert people["eid_cccccccc"]["metadata"]["role_rank"] == 6
    assert people["eid_aaaaaaaa"]["metadata"]["role_rank"] == 1
    # Engineer sits under their lead's team; the PM hangs off the VP.
    assert people["eid_aaaaaaaa"]["metadata"]["team_key"] == "team:eid_bbbbbbbb"
    assert people["eid_dddddddd"]["metadata"]["team_key"] == "team:eid_cccccccc"
    assert [m["external_id"] for m in modules] == ["demoforce"]
    assert modules[0]["subjects"] == ["module:demoforce"]
    # Every record validates against the canonical schema.
    for record in records:
        CanonicalRecord.model_validate(record)


def test_slack_rows_use_explicit_mentions_and_skip_bots_and_bad_dates(tmp_path: Path) -> None:
    _, _, prod = _write(tmp_path)
    rows = herb_slack_rows(prod)
    assert len(rows) == 1  # bot skipped, unparseable timestamp skipped
    row = rows[0]
    assert row["author_id"] == "eid_aaaaaaaa"
    assert row["mentions"] == ("eid_bbbbbbbb", "eid_dddddddd")  # self-mention dropped, sorted
    assert row["thread_parent_id"] is None  # HERB Slack has no threads
    assert row["module_keys"] == ("demoforce",)


def test_pr_rows_split_into_git_and_review_replies(tmp_path: Path) -> None:
    _, _, prod = _write(tmp_path)
    git_rows, review_rows = herb_pr_rows(prod)
    assert len(git_rows) == 1
    assert git_rows[0]["author_id"] == "eid_aaaaaaaa"
    assert git_rows[0]["module_keys"] == ("demoforce",)
    assert len(review_rows) == 2
    reviewer_to_parent = {r["author_id"]: r["parent_author_id"] for r in review_rows}
    assert reviewer_to_parent == {"eid_bbbbbbbb": "eid_aaaaaaaa", "EMP_123": "eid_aaaaaaaa"}
    # Review replies point at the PR's *git* artifact key so Gaps does not see a phantom.
    assert all(str(r["thread_parent_id"]).startswith("artifact:git:") for r in review_rows)
    # A review with an empty timestamp inherits the PR's timestamp instead of being dropped.
    emp_review = next(r for r in review_rows if r["author_id"] == "EMP_123")
    assert emp_review["occurred_at_epoch"] == git_rows[0]["occurred_at_epoch"]


def test_documents_become_ticket_rows(tmp_path: Path) -> None:
    _, _, prod = _write(tmp_path)
    rows = herb_document_rows(prod)
    assert len(rows) == 1
    assert rows[0]["reporter_id"] == "eid_dddddddd"
    assert rows[0]["title"] == "PRD"


def test_end_to_end_bundle_has_no_phantoms_and_resolves_eids(tmp_path: Path) -> None:
    emp, team, prod = _write(tmp_path)
    directory = tuple(
        CanonicalRecord.model_validate(r) for r in herb_directory_records(emp, team, ["DemoForce"])
    )
    git_rows, review_rows = herb_pr_rows(prod)
    bundle = ingest_exports(
        directory_records=directory,
        contracts=SequenceContractSet(),
        dataset_id="herb-test",
        slack_rows=(*herb_slack_rows(prod), *review_rows),
        ticket_rows=herb_document_rows(prod),
        git_rows=git_rows,
        identity_map={},
    )
    labels = {n.label for n in bundle.nodes}
    assert "Phantom" not in labels  # review parents exist as git artifacts
    people = {
        n.properties.get("display_name") or n.key for n in bundle.nodes if n.label == "Person"
    }
    assert "Priya Nair" in people and "Marcus Lee" in people
    # EMP_123 has no mapping and must be visibly unresolved, not silently dropped.
    unresolved = [
        n
        for n in bundle.nodes
        if n.label == "Person" and n.properties.get("identity_status") == "unresolved"
    ]
    assert len(unresolved) == 1
    assert any("EMP" in lim or "emp_123" in lim.lower() for lim in bundle.limitations)
    # Communication edges: mention (a→b, a→d) + review reply (b→a, EMP→a).
    comms = [e for e in bundle.edges if e.rel_type == "COMMUNICATES"]
    assert len(comms) >= 3
