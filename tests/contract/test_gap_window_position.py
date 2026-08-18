"""Phantoms are labelled by where the dangling reply sits in the export window.

A reply in the first ``EXPORT_BOUNDARY_DAYS`` of the corpus whose parent is missing is
almost certainly answering something from before the export began — an artefact of the
window. A reply deep inside the window with an absent parent is the corpus being
structurally incomplete. Both are reported; only the second is a finding.
"""

from __future__ import annotations

from xray_analytics import gap_findings
from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_ingest.gaps import EXPORT_BOUNDARY_DAYS
from xray_ingest.pipeline import ingest_exports

DAY = 86400
T0 = 1_735_689_600  # 2025-01-01


def _person(handle: str) -> CanonicalRecord:
    return CanonicalRecord.model_validate(
        {
            "author_external_id": None,
            "content": None,
            "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "external_id": handle,
            "kind": "directory_person",
            "metadata": {"display_name": handle.title(), "role_rank": 1, "team_key": "team:t"},
            "occurred_at_epoch": T0,
            "parent_external_id": None,
            "source": "test",
            "subjects": [f"person:{handle}"],
        }
    )


def _slack(msg_id: str, epoch: int, author: str, parent: str | None) -> dict[str, object]:
    return {
        "id": msg_id,
        "occurred_at_epoch": epoch,
        "author_id": author,
        "thread_parent_id": parent,
        "parent_author_id": None,
        "mentions": (),
        "module_keys": (),
        "text": None,
    }


def test_dangling_parents_are_split_into_boundary_and_in_window() -> None:
    bundle = ingest_exports(
        directory_records=(_person("alice"), _person("bob")),
        contracts=SequenceContractSet(),
        dataset_id="gap-window",
        slack_rows=(
            # corpus starts here
            _slack("m0", T0, "alice", None),
            # day 2: reply to a parent that is not in the export → boundary artefact
            _slack("m1", T0 + 2 * DAY, "bob", "missing-early"),
            # day 45: reply to a parent that should be here and is not → in-window gap
            _slack("m2", T0 + 45 * DAY, "alice", "missing-late"),
            # reply to a parent that *is* present → no phantom at all
            _slack("m3", T0 + 50 * DAY, "bob", "m0"),
        ),
        identity_map={},
    )
    phantoms = {n.canonical_key: n for n in bundle.nodes if n.label == "Phantom"}
    assert len(phantoms) == 2, sorted(phantoms)

    early = phantoms["artifact:slack:missing-early"].properties
    late = phantoms["artifact:slack:missing-late"].properties
    assert early["window_position"] == "export_boundary"
    assert early["days_after_corpus_start"] == 2
    assert late["window_position"] == "in_window"
    assert late["days_after_corpus_start"] == 45
    assert 2 <= EXPORT_BOUNDARY_DAYS < 45

    # The lens surfaces the label and puts in-window gaps first.
    findings = gap_findings(bundle)
    assert [f.window_position for f in findings] == ["in_window", "export_boundary"]
    assert findings[0].days_after_corpus_start == 45
