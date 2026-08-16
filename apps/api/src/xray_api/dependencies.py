from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from xray_core.models import CanonicalBundle, CanonicalRecord, SequenceContractSet
from xray_ingest.pipeline import ingest_exports

FIXTURE_ROOT = Path(__file__).parents[4] / "data" / "fixtures" / "xray-demo"
MIXED_FIXTURE_ROOT = Path(__file__).parents[4] / "data" / "fixtures" / "xray-mixed-v1"
SYNTH_FIXTURE_ROOT = Path(__file__).parents[4] / "data" / "fixtures" / "xray-synth-500"
DATASET_ID = "xray-demo-v1"
MIXED_DATASET_ID = "xray-mixed-v1"
SYNTH_DATASET_ID = "xray-synth-500"


def _canonical_fixture_bundle(root: Path, dataset_id: str) -> CanonicalBundle:
    records: list[CanonicalRecord] = []
    for name in ("directory.json", "events.json", "git_facts.json"):
        records.extend(
            CanonicalRecord.model_validate(payload)
            for payload in json.loads((root / name).read_text(encoding="utf-8"))
        )
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    contracts = SequenceContractSet.model_validate(
        {
            "contracts": manifest["sequence_contracts"],
            "limitations": manifest["limitations"],
        }
    )
    directory_records = tuple(record for record in records if record.kind == "directory_person")
    canonical_records = tuple(record for record in records if record.kind != "directory_person")
    return ingest_exports(
        directory_records=directory_records,
        canonical_records=canonical_records,
        contracts=contracts,
        dataset_id=dataset_id,
    )


@lru_cache(maxsize=1)
def demo_bundle() -> CanonicalBundle:
    return _canonical_fixture_bundle(FIXTURE_ROOT, DATASET_ID)


@lru_cache(maxsize=1)
def synth_bundle() -> CanonicalBundle:
    return _canonical_fixture_bundle(SYNTH_FIXTURE_ROOT, SYNTH_DATASET_ID)


@lru_cache(maxsize=1)
def mixed_bundle() -> CanonicalBundle:
    manifest = json.loads((MIXED_FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    directory_records = tuple(
        CanonicalRecord.model_validate(payload)
        for payload in json.loads(
            (MIXED_FIXTURE_ROOT / "directory.json").read_text(encoding="utf-8")
        )
    )
    return ingest_exports(
        directory_records=directory_records,
        contracts=SequenceContractSet.model_validate(
            {"contracts": manifest["sequence_contracts"], "limitations": manifest["limitations"]}
        ),
        dataset_id=MIXED_DATASET_ID,
        slack_rows=json.loads((MIXED_FIXTURE_ROOT / "slack.json").read_text(encoding="utf-8")),
        email_rows=json.loads((MIXED_FIXTURE_ROOT / "email.json").read_text(encoding="utf-8")),
        ticket_rows=json.loads((MIXED_FIXTURE_ROOT / "tickets.json").read_text(encoding="utf-8")),
        git_rows=json.loads((MIXED_FIXTURE_ROOT / "git.json").read_text(encoding="utf-8")),
    )


def current_snapshot_id() -> str:
    return f"{active_dataset_id()}:fixture"


def active_dataset_id() -> str:
    variant = os.environ.get("XRAY_FIXTURE_VARIANT")
    if variant == "mixed":
        return MIXED_DATASET_ID
    if variant == "synth500":
        return SYNTH_DATASET_ID
    return DATASET_ID


def active_bundle() -> CanonicalBundle:
    dataset_id = active_dataset_id()
    if dataset_id == MIXED_DATASET_ID:
        return mixed_bundle()
    if dataset_id == SYNTH_DATASET_ID:
        return synth_bundle()
    return demo_bundle()


__all__ = [
    "DATASET_ID",
    "MIXED_DATASET_ID",
    "SYNTH_DATASET_ID",
    "active_bundle",
    "active_dataset_id",
    "current_snapshot_id",
    "demo_bundle",
    "mixed_bundle",
    "synth_bundle",
]
