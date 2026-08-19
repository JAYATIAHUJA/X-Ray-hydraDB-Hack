"""Measure bounded-centrality ranking stability for maxLen 2 through 6 on a real snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from xray_analytics import bounded_shortest_path_tallies, communication_graph
from xray_ingest.manifest import read_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--json")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    snapshot_root = Path(args.snapshot)
    bundle = read_snapshot(snapshot_root)
    manifest = json.loads((snapshot_root / "manifest.json").read_text(encoding="utf-8"))
    graph = communication_graph(bundle)
    people = sorted(graph)
    rankings: dict[int, list[str]] = {}
    reachable_pairs: dict[int, int] = {}
    for max_len in range(2, 7):
        tallies, pairs = bounded_shortest_path_tallies(graph, people, max_len)
        reachable_pairs[max_len] = pairs
        rankings[max_len] = sorted(people, key=lambda key: (-tallies[key], key))
        print(f"max_len={max_len} reachable_pairs={pairs:,} top={rankings[max_len][0]}")

    baseline = set(rankings[4][: args.top])
    payload = {
        "dataset_id": bundle.dataset_id,
        "snapshot_id": manifest["snapshot_id"],
        "snapshot_content_sha256": manifest["content_sha256"],
        "method": "python_bounded_shortest_path_tallies",
        "people": len(people),
        "top_k": args.top,
        "baseline_max_len": 4,
        "results": {
            str(max_len): {
                "reachable_pairs": reachable_pairs[max_len],
                "top": rankings[max_len][: args.top],
                "top_k_overlap_with_max_len_4": round(
                    len(set(rankings[max_len][: args.top]) & baseline) / max(1, len(baseline)), 3
                ),
            }
            for max_len in rankings
        },
    }
    if args.json:
        output = Path(args.json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
