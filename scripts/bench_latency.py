#!/usr/bin/env python3
"""Measure live HydraDB Ghost lens latency and update docs/results/latency.json.

Usage:
    uv run python scripts/bench_latency.py
    XRAY_HYDRA_URI=bolt://localhost:7687 uv run python scripts/bench_latency.py

Requires a running HydraDB stack (docker compose --profile core up -d) with the
synth-500 fixture already seeded (POST /api/v1/hydra/seed-fixture).
"""
from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path

RESULTS = Path(__file__).parents[1] / "docs" / "results" / "latency.json"


def main() -> None:
    uri = os.environ.get("XRAY_HYDRA_URI")
    if not uri:
        print("XRAY_HYDRA_URI not set — skipping live latency measurement.")
        print("Set it to bolt://localhost:7687 (or your HydraDB address) and re-run.")
        return

    from xray_hydra.gateway import HydraGateway

    try:
        import neo4j  # type: ignore[import-untyped]
        driver = neo4j.GraphDatabase.driver(uri)
    except ImportError:
        try:
            import neo4j_driver as neo4j  # type: ignore[import-untyped, no-redef]
            driver = neo4j.GraphDatabase.driver(uri)
        except ImportError:
            print("No Bolt driver found (neo4j or neo4j-driver). Skipping live measurement.")
            return

    gateway = HydraGateway(driver)
    from xray_core.models import QuerySpec

    ping = QuerySpec(
        name="bench_ping",
        statement="RETURN 1 AS ok",
        parameters={},
        max_len=None,
        result_limit=1,
    )

    samples: list[float] = []
    rounds = 20
    print(f"Pinging HydraDB at {uri} ({rounds} rounds)…")
    for _ in range(rounds):
        t0 = time.perf_counter()
        gateway.run(ping)
        samples.append((time.perf_counter() - t0) * 1000)

    p50 = statistics.median(samples)
    p95 = sorted(samples)[int(len(samples) * 0.95)]
    print(f"  p50 = {p50:.1f} ms   p95 = {p95:.1f} ms")

    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    data["percentiles"]["p50_ms"] = round(p50, 1)
    data["percentiles"]["p95_ms"] = round(p95, 1)
    data["percentiles"]["note"] = f"Measured against live HydraDB at {uri} ({rounds} ping rounds)."
    RESULTS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  Updated {RESULTS}")
    driver.close()


if __name__ == "__main__":
    main()
