#!/usr/bin/env python3
"""PlanGraph-style baseline vs X-Ray on the labelled demo fixture.

This is an honest synthetic comparison of query shape and ownership reasoning,
not a claim that we beat the PlanGraph product on a shared enterprise corpus.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from pathlib import Path

from xray_analytics import faultlines, gap_findings, ghost_scores
from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_ingest.pipeline import ingest_exports

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "xray-demo-v2"
OUT = ROOT / "docs" / "results" / "plan-graph-baseline.json"


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


def _comm_graph(bundle) -> dict[str, set[str]]:
    nodes = {node.id: node.canonical_key for node in bundle.nodes}
    graph: dict[str, set[str]] = defaultdict(set)
    for edge in bundle.edges:
        if edge.rel_type != "COMMUNICATES":
            continue
        left = nodes[edge.source_id]
        right = nodes[edge.target_id]
        graph[left].add(right)
        graph[right].add(left)
    return graph


def _bfs(graph: dict[str, set[str]], start: str, goal: str, max_len: int = 4) -> int | None:
    if start == goal:
        return 0
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    seen = {start}
    while queue:
        node, dist = queue.popleft()
        if dist >= max_len:
            continue
        for neighbor in graph.get(node, ()):
            if neighbor in seen:
                continue
            if neighbor == goal:
                return dist + 1
            seen.add(neighbor)
            queue.append((neighbor, dist + 1))
    return None


def _naive_faultline_round_trips(bundle) -> dict[str, object]:
    """Client-style: one BFS per owner-owner pair on DEPENDS_ON edges."""
    nodes = {node.id: node.canonical_key for node in bundle.nodes}
    owners: dict[str, list[str]] = defaultdict(list)
    for edge in bundle.edges:
        if edge.rel_type != "OWNS":
            continue
        owners[nodes[edge.target_id]].append(nodes[edge.source_id])
    graph = _comm_graph(bundle)
    started = time.perf_counter()
    round_trips = 0
    naive_hits = 0
    for edge in bundle.edges:
        if edge.rel_type != "DEPENDS_ON":
            continue
        source = nodes[edge.source_id]
        target = nodes[edge.target_id]
        for left in owners.get(source, ()):
            for right in owners.get(target, ()):
                round_trips += 1
                if _bfs(graph, left, right) is None:
                    naive_hits += 1
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "method": "naive_per_pair_bfs",
        "round_trips": round_trips,
        "open_faultline_pairs": naive_hits,
        "wall_ms": round(elapsed_ms, 3),
    }


def _xray_faultlines(bundle) -> dict[str, object]:
    started = time.perf_counter()
    findings = faultlines(bundle)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "method": "xray_typed_faultlines",
        "round_trips": 1,
        "open_faultline_pairs": len(findings),
        "wall_ms": round(elapsed_ms, 3),
        "top_finding": (
            {
                "source_module_key": findings[0].source_module_key,
                "target_module_key": findings[0].target_module_key,
                "source_owner_key": findings[0].source_owner_key,
                "target_owner_key": findings[0].target_owner_key,
                "tier": findings[0].tier,
            }
            if findings
            else None
        ),
    }


def _naive_owner(bundle, module_key: str) -> str | None:
    """First OWNS edge by insertion order — ignores authority_rank."""
    nodes = {node.id: node.canonical_key for node in bundle.nodes}
    for edge in bundle.edges:
        if edge.rel_type != "OWNS" or nodes.get(edge.target_id) != module_key:
            continue
        return nodes[edge.source_id]
    return None


def _authority_owner(bundle, module_key: str) -> str | None:
    nodes = {node.id: node.canonical_key for node in bundle.nodes}
    ranked: list[tuple[int, str]] = []
    for edge in bundle.edges:
        if edge.rel_type != "OWNS" or nodes.get(edge.target_id) != module_key:
            continue
        rank = int(edge.properties.get("authority_rank", 0))
        ranked.append((rank, nodes[edge.source_id]))
    if not ranked:
        return None
    ranked.sort(reverse=True)
    return ranked[0][1]


def main() -> None:
    bundle = _load_bundle()
    ground = json.loads((FIXTURE / "ground_truth.json").read_text(encoding="utf-8"))
    module = ground["owner_conflict"]["module_key"]
    expected_primary = "person:maya-chen"
    naive = _naive_owner(bundle, module)
    authority = _authority_owner(bundle, module)
    payload = {
        "title": "PlanGraph-style baseline vs X-Ray",
        "fixture": "xray-demo-v2",
        "disclaimer": (
            "Synthetic fixture comparison of multi-query BFS / first-edge ownership "
            "versus X-Ray typed faultlines and authority-ranked ownership. "
            "Does not claim a head-to-head win against the PlanGraph product."
        ),
        "faultline_comparison": {
            "naive_client_style": _naive_faultline_round_trips(bundle),
            "xray": _xray_faultlines(bundle),
        },
        "ownership_conflict": {
            "module_key": module,
            "naive_first_edge_owner": naive,
            "xray_authority_ranked_owner": authority,
            "expected_primary_owner": expected_primary,
            "naive_correct": naive == expected_primary,
            "xray_correct": authority == expected_primary,
        },
        "supporting_lenses": {
            "gap_count": len(gap_findings(bundle)),
            "ghost_top": ghost_scores(bundle)[0].person_key if ghost_scores(bundle) else None,
        },
        "limitations": [
            "Measured on a labelled synthetic corpus, not a shared enterprise PlanGraph benchmark.",
            "Naïve round-trips count client BFS calls; a real PlanGraph deployment may batch differently.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "xray_correct": payload["ownership_conflict"]["xray_correct"]}, indent=2))


if __name__ == "__main__":
    main()
