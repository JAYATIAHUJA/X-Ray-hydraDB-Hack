from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from xray_core.models import CanonicalBundle, CanonicalRecord, SequenceContractSet
from xray_hydra import HydraGateway
from xray_ingest.manifest import read_snapshot
from xray_ingest.pipeline import ingest_exports

from .config import XraySettings, get_settings
from .hydra import create_gateway

logger = logging.getLogger(__name__)

FIXTURE_ROOT = Path(__file__).parents[4] / "data" / "fixtures" / "xray-demo"
DEMO_V2_FIXTURE_ROOT = Path(__file__).parents[4] / "data" / "fixtures" / "xray-demo-v2"
SYNTH_FIXTURE_ROOT = Path(__file__).parents[4] / "data" / "fixtures" / "xray-synth-500"
DATASET_ID = "xray-demo-v1"
DEMO_V2_DATASET_ID = "xray-demo-v2"
SYNTH_DATASET_ID = "xray-synth-500"

# XRAY_FIXTURE_VARIANT selects which bundled fixture the API serves. Only labelled
# fixtures with a complete lens surface (people, ownership, dependencies, gaps) are
# exposed here; adapter smoke data lives in tests, not behind a runtime flag.
FIXTURE_VARIANTS: dict[str, str] = {
    "demo": DATASET_ID,
    "demo-v2": DEMO_V2_DATASET_ID,
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
def demo_v2_bundle() -> CanonicalBundle:
    return _canonical_fixture_bundle(DEMO_V2_FIXTURE_ROOT, DEMO_V2_DATASET_ID)


@lru_cache(maxsize=1)
def synth_bundle() -> CanonicalBundle:
    return _canonical_fixture_bundle(SYNTH_FIXTURE_ROOT, SYNTH_DATASET_ID)


@lru_cache(maxsize=4)
def snapshot_bundle(root: str) -> CanonicalBundle:
    """A bundle read from an ingested snapshot directory (see scripts/ingest_export.py)."""
    return read_snapshot(Path(root))


def snapshot_dir() -> Path | None:
    value = os.environ.get("XRAY_SNAPSHOT_DIR", "").strip()
    return Path(value) if value else None


def current_snapshot_id() -> str:
    root = snapshot_dir()
    if root is not None:
        return f"{active_dataset_id()}:snapshot"
    return f"{active_dataset_id()}:fixture"


def active_dataset_id() -> str:
    root = snapshot_dir()
    if root is not None:
        return snapshot_bundle(str(root)).dataset_id
    variant = os.environ.get("XRAY_FIXTURE_VARIANT", "demo")
    return FIXTURE_VARIANTS.get(variant, DATASET_ID)


def active_bundle() -> CanonicalBundle:
    """The bundle the API serves.

    Precedence: ``XRAY_SNAPSHOT_DIR`` (any ingested corpus, e.g. the Apache Kafka run)
    > ``XRAY_FIXTURE_VARIANT`` (bundled labelled fixtures) > the demo fixture.
    """
    root = snapshot_dir()
    if root is not None:
        return snapshot_bundle(str(root))
    dataset_id = active_dataset_id()
    if dataset_id == SYNTH_DATASET_ID:
        return synth_bundle()
    if dataset_id == DEMO_V2_DATASET_ID:
        return demo_v2_bundle()
    return demo_bundle()


def get_gateway(
    settings: Annotated[XraySettings, Depends(get_settings)],
) -> Iterator[HydraGateway | None]:
    """Open one HydraDB gateway per request, or yield None in fixture mode.

    Tests override this dependency with a fake-driver gateway so the live lens
    code paths are exercised through HTTP. If the driver cannot be created the
    request degrades to fixture data and the failure is logged; the individual
    lens helpers still report ``degraded_reason`` when they retry and fail.
    """
    if not settings.hydra_configured:
        yield None
        return
    try:
        gateway = create_gateway(settings)
    except Exception:
        logger.exception("HydraDB gateway creation failed; serving fixture data")
        yield None
        return
    try:
        yield gateway
    finally:
        gateway.close()


__all__ = [
    "DATASET_ID",
    "DEMO_V2_DATASET_ID",
    "FIXTURE_VARIANTS",
    "SYNTH_DATASET_ID",
    "active_bundle",
    "active_dataset_id",
    "current_snapshot_id",
    "demo_bundle",
    "demo_v2_bundle",
    "get_gateway",
    "snapshot_bundle",
    "snapshot_dir",
    "synth_bundle",
]
