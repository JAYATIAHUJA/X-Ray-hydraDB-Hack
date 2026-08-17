from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from xray_core.models import CanonicalBundle, CanonicalRecord, SequenceContractSet
from xray_ingest.pipeline import ingest_exports

FIXTURE_ROOT = Path(__file__).parents[4] / "data" / "fixtures" / "xray-demo"
SYNTH_FIXTURE_ROOT = Path(__file__).parents[4] / "data" / "fixtures" / "xray-synth-500"
DATASET_ID = "xray-demo-v1"
SYNTH_DATASET_ID = "xray-synth-500"

# XRAY_FIXTURE_VARIANT selects which bundled fixture the API serves. Only labelled
# fixtures with a complete lens surface (people, ownership, dependencies, gaps) are
# exposed here; adapter smoke data lives in tests, not behind a runtime flag.
FIXTURE_VARIANTS: dict[str, str] = {
    "demo": DATASET_ID,
    "synth500": SYNTH_DATASET_ID,
}


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


def current_snapshot_id() -> str:
    return f"{active_dataset_id()}:fixture"


def active_dataset_id() -> str:
    variant = os.environ.get("XRAY_FIXTURE_VARIANT", "demo")
    return FIXTURE_VARIANTS.get(variant, DATASET_ID)


def active_bundle() -> CanonicalBundle:
    if active_dataset_id() == SYNTH_DATASET_ID:
        return synth_bundle()
    return demo_bundle()


__all__ = [
    "DATASET_ID",
    "FIXTURE_VARIANTS",
    "SYNTH_DATASET_ID",
    "active_bundle",
    "active_dataset_id",
    "current_snapshot_id",
    "demo_bundle",
    "synth_bundle",
]
