from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from xray_core.models import CanonicalBundle, CanonicalRecord, SequenceContractSet
from xray_ingest.pipeline import build_bundle

FIXTURE_ROOT = Path(__file__).parents[4] / "data" / "fixtures" / "xray-demo"
DATASET_ID = "xray-demo-v1"


@lru_cache(maxsize=1)
def demo_bundle() -> CanonicalBundle:
    records: list[CanonicalRecord] = []
    for name in ("directory.json", "events.json", "git_facts.json"):
        records.extend(
            CanonicalRecord.model_validate(payload)
            for payload in json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
        )
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    contracts = SequenceContractSet.model_validate(
        {
            "contracts": manifest["sequence_contracts"],
            "limitations": manifest["limitations"],
        }
    )
    return build_bundle(records, contracts, DATASET_ID)


def current_snapshot_id() -> str:
    return f"{DATASET_ID}:fixture"


__all__ = ["DATASET_ID", "current_snapshot_id", "demo_bundle"]
