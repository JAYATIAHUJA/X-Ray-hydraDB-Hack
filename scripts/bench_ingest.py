from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from neo4j import GraphDatabase
from xray_core.models import MAX_HYDRA_ID, Scalar
from xray_hydra import HydraGateway, edge_upsert_batch, node_upsert_batch

DEFAULT_BATCH_SIZES = (500, 1000, 2000, 5000)


def main() -> int:
    args = _parse_args()
    batch_sizes = _parse_batch_sizes(args.batch_sizes)
    uri = args.uri or os.environ.get("XRAY_HYDRA_URI") or "bolt://127.0.0.1:17687"
    user = args.user or os.environ.get("XRAY_HYDRA_USER") or "neo4j"
    password = (
        args.password or os.environ.get("XRAY_HYDRA_PASSWORD") or _runtime_password(args.runtime_id)
    )
    database = args.database or os.environ.get("XRAY_HYDRA_DATABASE") or "xray"

    if not password:
        print(
            "HydraDB password is required. Set XRAY_HYDRA_PASSWORD or run setup first.",
            file=sys.stderr,
        )
        return 2

    run_id = args.run_id or f"bench-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    auth = (user, password)
    driver = GraphDatabase.driver(uri, auth=auth, database=database)
    try:
        gateway = HydraGateway(driver)
        node_rows = _person_rows(run_id, args.people)
        started_nodes = time.perf_counter()
        gateway.run_batch(node_upsert_batch("Person", node_rows))
        node_seconds = time.perf_counter() - started_nodes

        results: list[BenchmarkResult] = []
        for batch_size in batch_sizes:
            rows = _communicates_rows(run_id, args.edges, args.people, batch_size)
            try:
                seconds = _time_edge_batches(gateway, rows, batch_size)
            except Exception as exc:
                results.append(
                    BenchmarkResult(
                        batch_size=batch_size,
                        edge_count=args.edges,
                        seconds=None,
                        edges_per_second=None,
                        error=str(exc),
                    )
                )
                continue
            results.append(
                BenchmarkResult(
                    batch_size=batch_size,
                    edge_count=args.edges,
                    seconds=seconds,
                    edges_per_second=args.edges / seconds,
                    error=None,
                )
            )
    finally:
        driver.close()

    successful = [result for result in results if result.edges_per_second is not None]
    if not successful:
        print("No batch size completed successfully.", file=sys.stderr)
        return 1
    winner = max(successful, key=lambda result: result.edges_per_second or 0.0)
    print(f"# HydraDB ingest benchmark ({run_id})")
    print()
    print(f"Node setup: {args.people:,} Person nodes in {node_seconds:.3f}s (not counted)")
    print()
    print("| Batch size | Edges | Seconds | Edges/sec | Status |")
    print("| ---: | ---: | ---: | ---: | --- |")
    for result in results:
        if result.seconds is None or result.edges_per_second is None:
            print(
                f"| {result.batch_size:,} | {result.edge_count:,} | - | - | failed: {_short_error(result.error)} |"
            )
        else:
            print(
                f"| {result.batch_size:,} | {result.edge_count:,} | "
                f"{result.seconds:.3f} | {result.edges_per_second:,.0f} | ok |"
            )
    print()
    print(f"Winner: batch_size={winner.batch_size:,}")
    return 0


class BenchmarkResult:
    def __init__(
        self,
        *,
        batch_size: int,
        edge_count: int,
        seconds: float | None,
        edges_per_second: float | None,
        error: str | None,
    ) -> None:
        self.batch_size = batch_size
        self.edge_count = edge_count
        self.seconds = seconds
        self.edges_per_second = edges_per_second
        self.error = error


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure live HydraDB COMMUNICATES ingest throughput via UNWIND batches."
    )
    parser.add_argument("--edges", type=int, default=10_000)
    parser.add_argument("--people", type=int, default=500)
    parser.add_argument(
        "--batch-sizes", default=",".join(str(size) for size in DEFAULT_BATCH_SIZES)
    )
    parser.add_argument("--runtime-id", default="runtime-demo")
    parser.add_argument("--run-id")
    parser.add_argument("--uri")
    parser.add_argument("--user")
    parser.add_argument("--password")
    parser.add_argument("--database")
    return parser.parse_args()


def _parse_batch_sizes(value: str) -> tuple[int, ...]:
    sizes = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not sizes or any(size <= 0 for size in sizes):
        raise SystemExit("--batch-sizes must contain positive integers")
    return sizes


def _runtime_password(runtime_id: str) -> str | None:
    path = Path("infra/runtime") / runtime_id / "hydra-auth-token"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def _person_rows(run_id: str, count: int) -> tuple[dict[str, Scalar], ...]:
    if count <= 1:
        raise SystemExit("--people must be greater than 1")
    rows: list[dict[str, Scalar]] = []
    seen: set[int] = set()
    for index in range(count):
        hydra_id = _id_for(run_id, "person", index)
        if hydra_id in seen:
            raise SystemExit("synthetic person id collision")
        seen.add(hydra_id)
        rows.append(
            {
                "id": hydra_id,
                "path_key": f"person:{hydra_id:020d}",
                "canonical_key": f"person:bench-{run_id}-{index:04d}@example.invalid",
                "dataset_id": run_id,
                "properties": json.dumps(
                    {
                        "confidence": 100,
                        "display_name": f"Bench Person {index:04d}",
                        "evidence_class": "demo_ground_truth",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
    return tuple(rows)


def _communicates_rows(
    run_id: str,
    count: int,
    people: int,
    batch_size: int,
) -> tuple[dict[str, Scalar], ...]:
    if count <= 0:
        raise SystemExit("--edges must be positive")
    rows: list[dict[str, Scalar]] = []
    seen: set[int] = set()
    for index in range(count):
        source_index = index % people
        target_index = (index * 17 + 23) % people
        if source_index == target_index:
            target_index = (target_index + 1) % people
        hydra_id = _id_for(run_id, "communicates", batch_size, index)
        if hydra_id in seen:
            raise SystemExit("synthetic edge id collision")
        seen.add(hydra_id)
        rows.append(
            {
                "id": hydra_id,
                "source_id": _id_for(run_id, "person", source_index),
                "target_id": _id_for(run_id, "person", target_index),
                "canonical_key": f"edge:bench-{run_id}-{batch_size}-{index:05d}",
                "dataset_id": run_id,
                "properties": json.dumps(
                    {
                        "batch_size": batch_size,
                        "confidence": 100,
                        "evidence_class": "demo_ground_truth",
                        "weight": 1,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
    return tuple(rows)


def _time_edge_batches(
    gateway: HydraGateway,
    rows: Sequence[dict[str, Scalar]],
    batch_size: int,
) -> float:
    durations: list[float] = []
    started = time.perf_counter()
    for offset in range(0, len(rows), batch_size):
        batch = edge_upsert_batch(
            "COMMUNICATES",
            rows[offset : offset + batch_size],
            source_label="Person",
            target_label="Person",
        )
        batch_started = time.perf_counter()
        gateway.run_batch(batch)
        durations.append(time.perf_counter() - batch_started)
    total_seconds = time.perf_counter() - started
    if durations:
        print(
            f"batch_size={batch_size:,}: median_batch_ms={statistics.median(durations) * 1000:.1f}",
            file=sys.stderr,
        )
    return total_seconds


def _id_for(*parts: object) -> int:
    digest = hashlib.blake2b(
        "|".join(str(part) for part in parts).encode("utf-8"),
        digest_size=8,
        person=b"xraybench",
    ).digest()
    return int.from_bytes(digest, "big") & MAX_HYDRA_ID


def _short_error(error: str | None) -> str:
    if not error:
        return "unknown"
    first_line = error.splitlines()[0]
    if "client_query_batch_items" in first_line:
        return "HydraDB admission control limit"
    return first_line[:80]


if __name__ == "__main__":
    raise SystemExit(main())
