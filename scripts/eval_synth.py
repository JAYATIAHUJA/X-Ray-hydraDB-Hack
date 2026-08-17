from __future__ import annotations

import argparse
import json
import random
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import networkx as nx
from xray_analytics.analysis import (
    bounded_shortest_path_tallies,
    communication_graph,
    faultlines,
    gap_findings,
    ghost_scores,
    reachable_pair_count,
    without_people,
)
from xray_api.dependencies import synth_bundle

DEFAULT_SEEDS = (11, 29, 47)
IMAGE_LOCK = Path("infra/runtime-images.lock")


def main() -> int:
    args = _parse_args()
    bundle = synth_bundle()
    truth = json.loads((Path(args.fixture_root) / "ground_truth.json").read_text(encoding="utf-8"))

    faultline_eval = _faultline_eval(bundle_findings=faultlines(bundle), truth=truth)
    gap_eval = _gap_eval(bundle_findings=gap_findings(bundle), truth=truth)
    ghost_eval = _ghost_eval(
        graph=communication_graph(bundle),
        planted_ghost=truth["ghost_person_key"],
        seeds=_parse_seeds(args.seeds),
        sample_pairs=args.sample_pairs,
        max_len=args.max_len,
    )

    client = _client_baseline(bundle, max_len=args.max_len)
    what_if = _what_if(bundle, truth["ghost_person_key"], max_len=args.max_len)

    if args.json is not None:
        _write_json(
            Path(args.json),
            {
                "dataset_id": bundle.dataset_id,
                "generated_at_utc": _utc_now(),
                "engine": _engine_stamp(),
                "graph": {"nodes": len(bundle.nodes), "edges": len(bundle.edges)},
                "parameters": {
                    "seeds": list(_parse_seeds(args.seeds)),
                    "sample_pairs": args.sample_pairs,
                    "max_len": args.max_len,
                },
                "faultline": _binary_payload(faultline_eval),
                "gap": _binary_payload(gap_eval),
                "ghost": {
                    "planted": truth["ghost_person_key"],
                    "top1_hit_rate": ghost_eval.top1_hit_rate,
                    "mean_top10_overlap_vs_exact": ghost_eval.mean_top10_overlap,
                    "runs": [
                        {
                            "seed": run.seed,
                            "top1": run.top1,
                            "planted_rank": run.planted_rank,
                            "top10_overlap": run.top10_overlap,
                        }
                        for run in ghost_eval.runs
                    ],
                    "what_if_remove_planted": what_if,
                },
                "client_baseline": client,
                "notes": [
                    "Planted-truth scoring on a labelled synthetic corpus; not a real-organization result.",
                    "The four coordinated dependencies are a negative control whose owners talk directly.",
                    "Absence in the corpus does not establish deletion.",
                ],
            },
        )

    print("# X-Ray synthetic evaluation")
    print()
    print(f"Dataset: `{bundle.dataset_id}`")
    print(f"Nodes: {len(bundle.nodes):,}")
    print(f"Edges: {len(bundle.edges):,}")
    print()
    print("| Metric | Value |")
    print("| --- | ---: |")
    print(f"| Faultline precision | {faultline_eval.precision:.3f} |")
    print(f"| Faultline recall | {faultline_eval.recall:.3f} |")
    print(
        f"| Faultlines planted / returned | {faultline_eval.true_positive} / {faultline_eval.returned} |"
    )
    print(f"| Gap precision | {gap_eval.precision:.3f} |")
    print(f"| Gap recall | {gap_eval.recall:.3f} |")
    print(f"| Gaps planted / returned | {gap_eval.true_positive} / {gap_eval.returned} |")
    print(f"| Ghost top-1 hit rate across seeds | {ghost_eval.top1_hit_rate:.3f} |")
    print(f"| Ghost mean top-10 overlap vs exact | {ghost_eval.mean_top10_overlap:.3f} |")
    print()
    print("Seeded ghost runs:")
    for run in ghost_eval.runs:
        print(
            f"- seed={run.seed}: top1={run.top1}, "
            f"planted_rank={run.planted_rank}, top10_overlap={run.top10_overlap:.3f}"
        )
    print()
    print(
        f"What-if (remove planted ghost): {what_if['pairs_lost']:,} of "
        f"{what_if['reachable_pairs_before']:,} reachable pairs lose a <= {args.max_len}-hop path."
    )
    print(
        f"Client baseline: bounded all-pairs BFS over {client['people']} people in "
        f"{client['ms']:.0f} ms (equivalent to {client['equivalent_round_trips']:,} "
        "per-pair shortest-path calls)."
    )
    if args.json is not None:
        print(f"Wrote {args.json}")
    return 0


@dataclass(frozen=True, slots=True)
class BinaryEval:
    returned: int
    planted: int
    true_positive: int

    @property
    def precision(self) -> float:
        return self.true_positive / float(self.returned or 1)

    @property
    def recall(self) -> float:
        return self.true_positive / float(self.planted or 1)


@dataclass(frozen=True, slots=True)
class GhostRun:
    seed: int
    top1: str
    planted_rank: int
    top10_overlap: float


@dataclass(frozen=True, slots=True)
class GhostEval:
    top1_hit_rate: float
    mean_top10_overlap: float
    runs: tuple[GhostRun, ...]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate X-Ray against xray-synth-500 ground truth."
    )
    parser.add_argument("--fixture-root", default="data/fixtures/xray-synth-500")
    parser.add_argument("--seeds", default=",".join(str(seed) for seed in DEFAULT_SEEDS))
    parser.add_argument("--sample-pairs", type=int, default=2_000)
    parser.add_argument("--max-len", type=int, default=4)
    parser.add_argument(
        "--json",
        default=None,
        help="Also write a machine-readable results file (e.g. docs/results/synth500.json).",
    )
    return parser.parse_args()


def _binary_payload(evaluation: BinaryEval) -> dict[str, Any]:
    return {
        "precision": evaluation.precision,
        "recall": evaluation.recall,
        "planted": evaluation.planted,
        "returned": evaluation.returned,
        "true_positive": evaluation.true_positive,
    }


def _client_baseline(bundle: Any, *, max_len: int) -> dict[str, Any]:
    graph = communication_graph(bundle)
    people = sorted(graph)
    started = time.perf_counter()
    bounded_shortest_path_tallies(graph, people, max_len)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "method": "python_bounded_bfs_all_pairs",
        "people": len(people),
        "ms": elapsed_ms,
        "equivalent_round_trips": len(people) * (len(people) - 1) // 2,
    }


def _what_if(bundle: Any, planted_key: str, *, max_len: int) -> dict[str, Any]:
    graph = communication_graph(bundle)
    before = reachable_pair_count(graph, max_len=max_len, excluding=(planted_key,))
    after = reachable_pair_count(
        communication_graph(without_people(bundle, (planted_key,))), max_len=max_len
    )
    top = ghost_scores(bundle, max_len=max_len)[0]
    return {
        "removed": planted_key,
        "reachable_pairs_before": before,
        "reachable_pairs_after": after,
        "pairs_lost": before - after,
        "top_structural": {
            "person_key": top.person_key,
            "display_name": top.display_name,
            "structural_rank": top.structural_rank,
            "formal_rank": top.formal_rank,
            "rank_gap": top.rank_gap,
        },
    }


def _engine_stamp() -> dict[str, Any]:
    if not IMAGE_LOCK.exists():
        return {"status": "image lock not found"}
    lock = json.loads(IMAGE_LOCK.read_text(encoding="utf-8"))
    hydra = lock.get("images", {}).get("hydradb", {})
    return {
        "repository": hydra.get("repository"),
        "digest": hydra.get("digest"),
        "source_commit": hydra.get("source_commit"),
        "license": hydra.get("license"),
        "note": "Synthetic evaluation runs in-process; the engine stamp records the pinned build the same numbers are demoed against.",
    }


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_seeds(value: str) -> tuple[int, ...]:
    seeds = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not seeds:
        raise SystemExit("--seeds must contain at least one integer")
    return seeds


def _faultline_eval(*, bundle_findings: tuple[Any, ...], truth: dict[str, Any]) -> BinaryEval:
    returned = {
        (finding.source_module_key, finding.target_module_key) for finding in bundle_findings
    }
    planted = {tuple(pair) for pair in truth["faultline_module_pairs"]}
    return BinaryEval(
        returned=len(returned),
        planted=len(planted),
        true_positive=len(returned & planted),
    )


def _gap_eval(*, bundle_findings: tuple[Any, ...], truth: dict[str, Any]) -> BinaryEval:
    returned = {finding.phantom_key for finding in bundle_findings}
    planted = {path["phantom_key"] for path in truth["gap_paths"]}
    return BinaryEval(
        returned=len(returned),
        planted=len(planted),
        true_positive=len(returned & planted),
    )


def _ghost_eval(
    *,
    graph: dict[str, dict[str, int]],
    planted_ghost: str,
    seeds: tuple[int, ...],
    sample_pairs: int,
    max_len: int,
) -> GhostEval:
    exact_top10 = _exact_top10(graph)
    runs = tuple(
        _sampled_ghost_run(
            graph=graph,
            planted_ghost=planted_ghost,
            exact_top10=exact_top10,
            seed=seed,
            sample_pairs=sample_pairs,
            max_len=max_len,
        )
        for seed in seeds
    )
    return GhostEval(
        top1_hit_rate=sum(run.top1 == planted_ghost for run in runs) / len(runs),
        mean_top10_overlap=sum(run.top10_overlap for run in runs) / len(runs),
        runs=runs,
    )


def _exact_top10(graph: dict[str, dict[str, int]]) -> tuple[str, ...]:
    nx_graph = nx.Graph()
    for source, neighbors in graph.items():
        nx_graph.add_node(source)
        for target in neighbors:
            nx_graph.add_edge(source, target)
    scores = nx.betweenness_centrality(nx_graph, normalized=True)
    return tuple(sorted(scores, key=lambda key: (-scores[key], key))[:10])


def _sampled_ghost_run(
    *,
    graph: dict[str, dict[str, int]],
    planted_ghost: str,
    exact_top10: tuple[str, ...],
    seed: int,
    sample_pairs: int,
    max_len: int,
) -> GhostRun:
    rng = random.Random(seed)
    people = sorted(graph)
    all_pairs = list(combinations(people, 2))
    pairs = rng.sample(all_pairs, min(sample_pairs, len(all_pairs)))
    tallies = dict.fromkeys(people, 0.0)
    reachable = 0
    for source, target in pairs:
        path = _shortest_path(graph, source, target, max_len)
        if not path:
            continue
        reachable += 1
        for intermediate in path[1:-1]:
            tallies[intermediate] += 1.0
    denominator = float(reachable or 1)
    ordered = sorted(people, key=lambda key: (-(tallies[key] / denominator), key))
    top10 = tuple(ordered[:10])
    return GhostRun(
        seed=seed,
        top1=ordered[0],
        planted_rank=ordered.index(planted_ghost) + 1,
        top10_overlap=len(set(top10) & set(exact_top10)) / 10.0,
    )


def _shortest_path(
    graph: dict[str, dict[str, int]], source: str, target: str, max_len: int
) -> tuple[str, ...]:
    queue: deque[tuple[str, ...]] = deque([(source,)])
    seen = {source}
    while queue:
        path = queue.popleft()
        if len(path) - 1 >= max_len:
            continue
        for neighbor in sorted(graph[path[-1]]):
            if neighbor in seen:
                continue
            next_path = (*path, neighbor)
            if neighbor == target:
                return next_path
            seen.add(neighbor)
            queue.append(next_path)
    return ()


if __name__ == "__main__":
    raise SystemExit(main())
