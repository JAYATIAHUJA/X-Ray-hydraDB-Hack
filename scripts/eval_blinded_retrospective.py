#!/usr/bin/env python3
"""Blinded retrospective harness.

Predictions are computed before sealed labels are opened. Labels live in
``data/eval/blinded_labels.json`` and must not be consulted during prediction.
"""

from __future__ import annotations

import json
from pathlib import Path

from xray_analytics import faultlines, gap_findings, ghost_scores, identity_candidates
from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_ingest.pipeline import ingest_exports

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "xray-demo-v2"
LABELS = ROOT / "data" / "eval" / "blinded_labels.json"
OUT = ROOT / "docs" / "results" / "blinded-retrospective.json"


def _load_bundle():
    records: list[CanonicalRecord] = []
    for name in ("directory.json", "events.json", "git_facts.json"):
        records.extend(
            CanonicalRecord.model_validate(payload)
            for payload in json.loads((FIXTURE / name).read_text(encoding="utf-8"))
        )
    manifest = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    contracts = SequenceContractSet.model_validate(
        {"contracts": manifest["sequence_contracts"], "limitations": manifest["limitations"]}
    )
    directory = tuple(record for record in records if record.kind == "directory_person")
    canonical = tuple(record for record in records if record.kind != "directory_person")
    return ingest_exports(
        directory_records=directory,
        canonical_records=canonical,
        contracts=contracts,
        dataset_id="xray-demo-v2",
    )


def _predict(bundle) -> dict[str, object]:
    """Phase 1 — sealed. Do not read LABEL files here."""
    ghosts = ghost_scores(bundle)
    gaps = gap_findings(bundle)
    lines = faultlines(bundle)
    identities = identity_candidates(bundle)
    owners = {}
    nodes = {node.id: node.canonical_key for node in bundle.nodes}
    ranked: dict[str, list[tuple[int, str]]] = {}
    for edge in bundle.edges:
        if edge.rel_type != "OWNS":
            continue
        module = nodes[edge.target_id]
        ranked.setdefault(module, []).append(
            (int(edge.properties.get("authority_rank", 0)), nodes[edge.source_id])
        )
    for module, values in ranked.items():
        values.sort(reverse=True)
        owners[module] = values[0][1]
    return {
        "ghost_person_key": ghosts[0].person_key if ghosts else None,
        "phantom_key": gaps[0].phantom_key if gaps else None,
        "faultline_modules": (
            [lines[0].source_module_key, lines[0].target_module_key] if lines else []
        ),
        "primary_owner_payments": owners.get("module:payments-api"),
        "identity_candidate_id": identities[0].candidate_id if identities else None,
    }


def _score(predictions: dict[str, object], labels: dict[str, object]) -> dict[str, object]:
    checks = {
        "ghost_person_key": predictions.get("ghost_person_key") == labels.get("ghost_person_key"),
        "phantom_key": predictions.get("phantom_key") == labels.get("phantom_key"),
        "faultline_modules": predictions.get("faultline_modules") == labels.get("faultline_modules"),
        "primary_owner_payments": predictions.get("primary_owner_payments")
        == labels.get("primary_owner_payments"),
        "identity_candidate_id": predictions.get("identity_candidate_id")
        == labels.get("identity_candidate_id"),
    }
    correct = sum(1 for value in checks.values() if value)
    return {
        "checks": checks,
        "correct": correct,
        "total": len(checks),
        "accuracy": correct / len(checks) if checks else 0.0,
    }


def main() -> None:
    bundle = _load_bundle()
    predictions = _predict(bundle)
    # Phase 2 — open sealed labels only after predictions are frozen.
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    score = _score(predictions, labels["answers"])
    payload = {
        "title": "Blinded retrospective (synthetic hold-out)",
        "fixture": "xray-demo-v2",
        "labels_file": str(LABELS.relative_to(ROOT)),
        "protocol": [
            "Compute predictions without reading blinded_labels.json",
            "Open labels only after predictions are frozen",
            "Score exact-match on sealed answer keys",
        ],
        "predictions": predictions,
        "score": score,
        "limitations": labels.get("limitations", []),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "accuracy": score["accuracy"]}, indent=2))


if __name__ == "__main__":
    main()
