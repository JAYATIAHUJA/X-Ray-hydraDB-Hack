"""Evaluate X-Ray on an ingested real corpus and write a traceable results file.

Unlike ``eval_synth.py`` there is no planted truth here. This script records what the
lenses *return* on a real snapshot, plus the structural facts a reader needs to judge
them (identity coverage, phantom counts, negative results), stamped with the pinned
engine build. Numbers in the README must trace to the output file.

    uv run python scripts/eval_corpus.py --snapshot data/snapshots/kafka-2025q2 \\
        --json docs/results/kafka-2025q2.json
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xray_analytics import (
    bounded_shortest_path_tallies,
    communication_graph,
    faultlines,
    gap_findings,
    ghost_scores,
    reachable_pair_count,
    without_people,
)
from xray_ingest.manifest import read_snapshot

IMAGE_LOCK = Path("infra/runtime-images.lock")


def main() -> int:
    args = _parse_args()
    root = Path(args.snapshot)
    bundle = read_snapshot(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    max_len = args.max_len

    people = [n for n in bundle.nodes if n.label == "Person"]
    unresolved = [n for n in people if n.properties.get("identity_status") == "unresolved"]
    role_counts = Counter(int(n.properties.get("role_rank", 0)) for n in people)
    edge_counts = Counter(e.rel_type for e in bundle.edges)
    node_counts = Counter(n.label for n in bundle.nodes)

    graph = communication_graph(bundle)
    started = time.perf_counter()
    bounded_shortest_path_tallies(graph, sorted(graph), max_len)
    client_ms = (time.perf_counter() - started) * 1000

    scores = ghost_scores(bundle, max_len=max_len)
    top = scores[0]
    before = reachable_pair_count(graph, max_len=max_len, excluding=(top.person_key,))
    after = reachable_pair_count(
        communication_graph(without_people(bundle, (top.person_key,))), max_len=max_len
    )
    largest_gap = max(scores[: args.top], key=lambda s: s.rank_gap)

    findings = faultlines(bundle, max_len=max_len)
    tiers = Counter(f.tier for f in findings)
    gaps = gap_findings(bundle)
    gap_reasons = Counter(g.reason for g in gaps)

    payload: dict[str, Any] = {
        "dataset_id": bundle.dataset_id,
        "snapshot_id": manifest.get("snapshot_id"),
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "engine": _engine_stamp(),
        "graph": {
            "nodes": len(bundle.nodes),
            "edges": len(bundle.edges),
            "node_counts": dict(sorted(node_counts.items())),
            "edge_counts": dict(sorted(edge_counts.items())),
        },
        "identity": {
            "people": len(people),
            "unresolved": len(unresolved),
            "role_rank_counts": dict(sorted(role_counts.items())),
            "note": "role_rank from the public ASF roster: 4=PMC, 3=committer, 1=contributor.",
        },
        "parameters": {"max_len": max_len},
        "ghost": {
            "top": [
                {
                    "person_key": s.person_key,
                    "display_name": s.display_name,
                    "role_rank": s.role_rank,
                    "structural_rank": s.structural_rank,
                    "formal_rank": s.formal_rank,
                    "rank_gap": s.rank_gap,
                    "sampled_centrality": round(s.sampled_centrality, 4),
                    "communication_degree": s.communication_degree,
                }
                for s in scores[: args.top]
            ],
            "largest_rank_gap_in_top": {
                "display_name": largest_gap.display_name,
                "structural_rank": largest_gap.structural_rank,
                "formal_rank": largest_gap.formal_rank,
                "rank_gap": largest_gap.rank_gap,
            },
            "what_if_remove_top": {
                "removed": top.display_name,
                "reachable_pairs_before": before,
                "reachable_pairs_after": after,
                "pairs_lost": before - after,
            },
        },
        "faultline": {
            "count": len(findings),
            "tiers": dict(sorted(tiers.items())),
            "top": [
                {
                    "source_module": f.source_module_key,
                    "target_module": f.target_module_key,
                    "dependency_weight": f.dependency_weight,
                    "source_owner": f.source_owner_key,
                    "target_owner": f.target_owner_key,
                    "communication_distance": f.communication_distance,
                    "tier": f.tier,
                    "severity": f.severity,
                }
                for f in findings[: args.top]
            ],
            "incident_lift": {
                "status": "not_measurable",
                "reason": (
                    "The corpus carries no module-linked incident signal (Kafka JIRA issues in "
                    "the window have no components), so no lift over a churn baseline is claimed. "
                    "Faultlines are reported as coordination debt only."
                ),
            },
        },
        "gaps": {
            "phantoms": sum(1 for n in bundle.nodes if n.label == "Phantom"),
            "reasons": dict(sorted(gap_reasons.items())),
            "note": (
                "Dangling thread parents are replies whose parent message is outside the export "
                "window; absence in the corpus does not establish deletion."
            ),
        },
        "client_baseline": {
            "method": "python_bounded_bfs_all_pairs",
            "people": len(graph),
            "ms": round(client_ms, 1),
            "equivalent_round_trips": len(graph) * (len(graph) - 1) // 2,
        },
        "limitations": list(bundle.limitations),
    }

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"# X-Ray corpus evaluation: {bundle.dataset_id}")
    print(
        f"nodes={len(bundle.nodes)} edges={len(bundle.edges)} people={len(people)} unresolved={len(unresolved)}"
    )
    print("Ghost top:")
    for s in scores[: args.top]:
        print(
            f"  {s.display_name:<26} role={s.role_rank} structural#{s.structural_rank:<3} "
            f"formal#{s.formal_rank:<3} gap={s.rank_gap:+d}"
        )
    print(
        f"What-if remove {top.display_name}: {before - after:,} of {before:,} reachable pairs lose a <= {max_len}-hop path"
    )
    print(f"Faultlines: {len(findings)} ({dict(tiers)}); phantoms: {payload['gaps']['phantoms']}")
    for f in findings[:5]:
        print(
            f"  {f.source_module_key[7:]:<18} -> {f.target_module_key[7:]:<18} w={f.dependency_weight} owners={f.source_owner_key[7:]}/{f.target_owner_key[7:]} dist={f.communication_distance}"
        )
    if args.json:
        print(f"Wrote {args.json}")
    return 0


def _engine_stamp() -> dict[str, Any]:
    if not IMAGE_LOCK.exists():
        return {"status": "image lock not found"}
    lock = json.loads(IMAGE_LOCK.read_text(encoding="utf-8"))
    hydra = lock.get("images", {}).get("hydradb", {})
    return {
        "repository": hydra.get("repository"),
        "digest": hydra.get("digest"),
        "source_commit": hydra.get("source_commit"),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--json", default=None)
    parser.add_argument("--max-len", type=int, default=4)
    parser.add_argument("--top", type=int, default=10)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
