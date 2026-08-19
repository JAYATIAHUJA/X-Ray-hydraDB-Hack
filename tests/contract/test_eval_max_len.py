from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_ingest.manifest import write_snapshot
from xray_ingest.pipeline import build_bundle

FIXTURE_ROOT = Path(__file__).parents[2] / "data" / "fixtures" / "xray-demo"


def test_eval_max_len_emits_auditable_snapshot_results(tmp_path: Path) -> None:
    records = tuple(
        CanonicalRecord.model_validate(item)
        for name in ("directory.json", "events.json", "git_facts.json")
        for item in json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    )
    fixture_manifest = json.loads(
        (FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8")
    )
    contracts = SequenceContractSet.model_validate(
        {
            "contracts": fixture_manifest["sequence_contracts"],
            "limitations": fixture_manifest["limitations"],
        }
    )
    snapshot_root = tmp_path / "snapshot"
    manifest = write_snapshot(build_bundle(records, contracts, "max-len-test"), snapshot_root)
    output = tmp_path / "max-len.json"

    subprocess.run(
        [
            sys.executable,
            "scripts/eval_max_len.py",
            "--snapshot",
            str(snapshot_root),
            "--json",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["snapshot_id"] == manifest.snapshot_id
    assert payload["snapshot_content_sha256"] == manifest.content_sha256
    assert payload["method"] == "python_bounded_shortest_path_tallies"
    assert set(payload["results"]) == {"2", "3", "4", "5", "6"}
    assert all(result["reachable_pairs"] >= 0 for result in payload["results"].values())
