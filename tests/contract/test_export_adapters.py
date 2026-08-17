from __future__ import annotations

import json
import mailbox
from email.message import EmailMessage
from pathlib import Path

from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_ingest.adapters import git_log_rows, jira_csv_rows, mbox_rows, slack_export_rows
from xray_ingest.pipeline import ingest_exports


def test_mbox_adapter_maps_explicit_headers_to_email_rows(tmp_path: Path) -> None:
    path = tmp_path / "mailbox.mbox"
    box = mailbox.mbox(path)
    message = EmailMessage()
    message["Message-ID"] = "<msg-1@example.test>"
    message["Date"] = "Wed, 01 Jan 2025 00:00:00 +0000"
    message["From"] = "Alex <alex@example.test>"
    message["To"] = "Maya <maya@example.test>"
    message["Subject"] = "Payments rollout"
    message.set_content("Please review.")
    box.add(message)
    box.flush()

    rows = mbox_rows(path, module_keys_by_message_id={"msg-1@example.test": ("payments-api",)})

    assert rows == (
        {
            "id": "msg-1@example.test",
            "occurred_at_epoch": 1735689600,
            "from_id": "alex@example.test",
            "to_ids": ("maya@example.test",),
            "in_reply_to_id": None,
            "subject": "Payments rollout",
            "body": "Please review.",
            "module_keys": ("payments-api",),
        },
    )


def test_jira_csv_adapter_maps_rows_to_ticket_rows(tmp_path: Path) -> None:
    path = tmp_path / "jira.csv"
    path.write_text(
        "key,created,reporter_id,summary,description,components\n"
        "PAY-1,2025-01-01T00:00:00+00:00,maya,Retry bug,Intermittent failure,payments-api;ledger-worker\n",
        encoding="utf-8",
    )

    assert jira_csv_rows(path) == (
        {
            "id": "PAY-1",
            "occurred_at_epoch": 1735689600,
            "reporter_id": "maya",
            "title": "Retry bug",
            "body": "Intermittent failure",
            "module_keys": ("ledger-worker", "payments-api"),
        },
    )


def test_git_log_adapter_maps_changed_paths_to_modules(tmp_path: Path) -> None:
    path = tmp_path / "git.log"
    path.write_text(
        "abc123\x1f1735689600\x1falex@example.test\x1fTouch payment and ledger\n"
        "services/payments/app.py\n"
        "services/ledger/worker.py\n",
        encoding="utf-8",
    )

    assert git_log_rows(
        path,
        module_prefixes={
            "services/ledger": "ledger-worker",
            "services/payments": "payments-api",
        },
    ) == (
        {
            "sha": "abc123",
            "occurred_at_epoch": 1735689600,
            "author_id": "alex@example.test",
            "message": "Touch payment and ledger",
            "module_keys": ("ledger-worker", "payments-api"),
            "dependency_keys": (),
        },
    )


def test_slack_export_adapter_maps_threads_and_mentions(tmp_path: Path) -> None:
    channel_dir = tmp_path / "payments"
    channel_dir.mkdir()
    (channel_dir / "2025-01-01.json").write_text(
        json.dumps(
            [
                {"ts": "1735689600.000100", "user": "U_ALEX", "text": "parent"},
                {
                    "ts": "1735689660.000200",
                    "thread_ts": "1735689600.000100",
                    "user": "U_MAYA",
                    "text": "reply <@U_PRIYA>",
                },
            ]
        ),
        encoding="utf-8",
    )

    rows = slack_export_rows(tmp_path, module_keys_by_channel={"payments": ("payments-api",)})

    assert rows[1] == {
        "id": "payments-1735689660.000200",
        "occurred_at_epoch": 1735689660,
        "author_id": "U_MAYA",
        "thread_parent_id": "payments-1735689600.000100",
        "parent_author_id": "U_ALEX",
        "mentions": ("U_PRIYA",),
        "module_keys": ("payments-api",),
        "text": "reply <@U_PRIYA>",
    }


def test_export_adapter_rows_feed_existing_ingest_pipeline(tmp_path: Path) -> None:
    git_path = tmp_path / "git.log"
    git_path.write_text(
        "abc123\x1f1735689600\x1falex\x1fTouch payment and ledger\n"
        "services/payments/app.py\n"
        "services/ledger/worker.py\n",
        encoding="utf-8",
    )
    bundle = ingest_exports(
        directory_records=(
            _person_record("alex"),
            *_module_records("payments-api", "ledger-worker"),
        ),
        contracts=SequenceContractSet(),
        dataset_id="adapter-pipeline-test",
        git_rows=git_log_rows(
            git_path,
            module_prefixes={
                "services/ledger": "ledger-worker",
                "services/payments": "payments-api",
            },
        ),
    )

    assert any(
        edge.canonical_key == "depends_on:ledger-worker:payments-api:cochange"
        for edge in bundle.edges
    )


def _module_records(*modules: str):
    for module in modules:
        yield CanonicalRecord.model_validate(
            {
                "source": "directory",
                "external_id": module,
                "kind": "module",
                "occurred_at_epoch": 1,
                "author_external_id": None,
                "parent_external_id": None,
                "subjects": [f"module:{module}"],
                "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "content": None,
                "metadata": {"canonical_key": f"module:{module}"},
            }
        )


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


def test_all_four_adapters_compose_with_identity_map_and_unresolved_ids(tmp_path: Path) -> None:
    # --- mbox: sender is an email address mapped to a handle; one recipient is unknown.
    mbox_path = tmp_path / "dev.mbox"
    box = mailbox.mbox(mbox_path)
    message = EmailMessage()
    message["Message-ID"] = "<m1@example.test>"
    message["Date"] = "Wed, 01 Jan 2025 00:00:00"  # naive date -> treated as UTC
    message["From"] = "Alex <Alex@Example.test>"
    message["To"] = "maya@example.test, stranger@example.test"
    message["Subject"] = "Ledger retry"
    message.set_content("thread")
    box.add(message)
    box.flush()

    # --- git: 0x1e-separated with a multi-line body and a Depends-On trailer.
    git_path = tmp_path / "git.log"
    git_path.write_text(
        "\x1eabc123\x1f1735689600\x1fALEX@example.test\x1fTouch payments\x1f"
        "Longer body.\n\nDepends-On: ledger-worker\n"
        "services/payments/app.py\n"
        "\x1edef456\x1f1735689700\x1fmaya@example.test\x1fLedger fix\x1f\n"
        "services/ledger/worker.py\n",
        encoding="utf-8",
    )

    # --- jira
    jira_path = tmp_path / "jira.csv"
    jira_path.write_text(
        "key,created,reporter_id,summary,description,components\n"
        "PAY-1,2025-01-01T00:00:00+00:00,U_MAYA,Retry bug,Fails,payments-api\n",
        encoding="utf-8",
    )

    # --- slack: reply whose parent is NOT in the export (dangling parent -> Phantom).
    channel_dir = tmp_path / "slack" / "payments"
    channel_dir.mkdir(parents=True)
    (channel_dir / "2025-01-01.json").write_text(
        json.dumps(
            [
                {
                    "ts": "1735689660.000200",
                    "thread_ts": "1735689600.000100",
                    "user": "U_MAYA",
                    "text": "reply <@U_ALEX>",
                }
            ]
        ),
        encoding="utf-8",
    )

    bundle = ingest_exports(
        directory_records=(
            _person_record("alex"),
            _person_record("maya"),
            *_module_records("payments-api", "ledger-worker"),
        ),
        contracts=SequenceContractSet(),
        dataset_id="adapter-e2e",
        email_rows=mbox_rows(mbox_path),
        ticket_rows=jira_csv_rows(jira_path),
        git_rows=git_log_rows(
            git_path,
            module_prefixes={
                "services/ledger": "ledger-worker",
                "services/payments": "payments-api",
            },
        ),
        slack_rows=slack_export_rows(tmp_path / "slack"),
        identity_map={
            "alex@example.test": "alex",
            "maya@example.test": "maya",
            "U_ALEX": "alex",
            "U_MAYA": "maya",
        },
    )

    people = {node.canonical_key: node for node in bundle.nodes if node.label == "Person"}
    # Mapped ids collapse onto directory handles; the unknown recipient is kept, visibly.
    assert {"person:alex", "person:maya"} <= set(people)
    unresolved = [key for key, node in people.items() if node.properties.get("identity_status")]
    assert len(unresolved) == 1 and unresolved[0].startswith("person:unresolved-stranger-")
    assert people[unresolved[0]].properties["display_name"] == "stranger@example.test"
    assert any("not in the identity map" in item for item in bundle.limitations)

    edge_keys = {edge.canonical_key for edge in bundle.edges}
    # Email + Slack communication landed on the *handles*, not raw ids.
    assert any(k.startswith("communicates:alex:maya") for k in edge_keys)
    # Explicit dependency from the Depends-On trailer plus authorship on both modules.
    assert any(k.startswith("depends_on:payments-api:ledger-worker") for k in edge_keys)
    # Dangling Slack parent materialised as a Phantom.
    assert any(node.label == "Phantom" for node in bundle.nodes)
    # Naive mbox date treated as UTC.
    email_artifacts = [
        n for n in bundle.nodes if n.label == "Artifact" and "m1@example.test" in n.canonical_key
    ]
    assert email_artifacts and email_artifacts[0].properties["created_epoch"] == 1735689600
