from __future__ import annotations

import json
import shutil
from pathlib import Path

from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_hydra import HydraGateway, HydraLoader
from xray_ingest.manifest import write_snapshot
from xray_ingest.pipeline import build_bundle

FIXTURE_ROOT = Path(__file__).parents[2] / "data" / "fixtures" / "xray-demo"
WORK_ROOT = Path(__file__).parents[2] / ".cache" / "contract-loader"


class RecordingDriver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append((query_, parameters_))
        return [{"count": len((parameters_ or {}).get("rows", []))}]


def demo_snapshot() -> tuple[Path, object]:
    if WORK_ROOT.exists():
        shutil.rmtree(WORK_ROOT)
    WORK_ROOT.mkdir(parents=True)
    records: list[CanonicalRecord] = []
    for name in ("directory.json", "events.json", "git_facts.json"):
        records.extend(
            CanonicalRecord.model_validate(payload)
            for payload in json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
        )
    manifest_payload = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    contracts = SequenceContractSet.model_validate(
        {
            "contracts": manifest_payload["sequence_contracts"],
            "limitations": manifest_payload["limitations"],
        }
    )
    bundle = build_bundle(records, contracts, "xray-demo-v1")
    manifest = write_snapshot(bundle, WORK_ROOT / "snapshot")
    return WORK_ROOT / "snapshot", manifest


def test_loader_validates_snapshot_and_loads_nodes_before_edges() -> None:
    snapshot_dir, manifest = demo_snapshot()
    driver = RecordingDriver()
    loader = HydraLoader(HydraGateway(driver))

    report = loader.load(snapshot_dir, manifest, batch_size=500)

    assert report.node_count == 17
    assert report.edge_count == 30
    assert report.completed_batches == report.attempted_batches
    assert report.failed_batches == ()
    first_edge_index = next(
        index for index, call in enumerate(driver.calls) if "MERGE (s)-[r:" in call[0]
    )
    assert all("MERGE (n {id: row.id})" in call[0] for call in driver.calls[:first_edge_index])
    assert any("MATCH (s:Person {id: row.source_id})" in call[0] for call in driver.calls)


def test_loader_resumes_previously_completed_batches() -> None:
    snapshot_dir, manifest = demo_snapshot()
    driver = RecordingDriver()
    loader = HydraLoader(HydraGateway(driver))

    first = loader.load(snapshot_dir, manifest, batch_size=500)
    second = loader.load(snapshot_dir, manifest, batch_size=500)

    assert second.graph_fingerprint == first.graph_fingerprint
    assert second.resumed_batches == first.attempted_batches
    assert len(driver.calls) == first.attempted_batches
