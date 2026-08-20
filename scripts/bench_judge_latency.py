"""Measure live HydraDB latency using the three Judge Mode ontology queries."""

from __future__ import annotations

import json
import math
import os
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from xray_hydra import HydraGateway, ontology_context_query

RESULTS = Path(__file__).parents[1] / "docs" / "results" / "judge-latency.json"
QUERIES = (
    ontology_context_query("owner", "xray-demo-v1", "module:payments-api"),
    ontology_context_query("dependency_impact", "xray-demo-v1", "module:ledger-worker"),
    ontology_context_query("approval", "xray-demo-v1", "artifact:missing-approval"),
)


def main() -> int:
    uri = os.environ.get("XRAY_HYDRA_URI")
    if not uri:
        raise SystemExit("XRAY_HYDRA_URI is required; refusing to fabricate live latency.")
    from neo4j import GraphDatabase

    user = os.environ.get("XRAY_HYDRA_USER")
    password = os.environ.get("XRAY_HYDRA_PASSWORD")
    auth = None if user is None and password is None else (user or "", password or "")
    driver = GraphDatabase.driver(uri, auth=auth)
    gateway = HydraGateway(driver)
    samples: dict[str, list[float]] = {query.name: [] for query in QUERIES}
    try:
        for query in QUERIES:
            for _ in range(3):
                rows = gateway.run(query)
                if not rows:
                    raise RuntimeError(
                        f"{query.name} returned no rows; seed the xray-demo-v1 graph first."
                    )
            for _ in range(20):
                started = time.perf_counter()
                gateway.run(query)
                samples[query.name].append((time.perf_counter() - started) * 1000)
    finally:
        gateway.close()

    combined = [sample for values in samples.values() for sample in values]
    payload = {
        "dataset_id": "xray-demo-v1",
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "method": "20 timed executions after 3 warmups for each Judge Mode ontology query.",
        "endpoint": uri,
        "round_trips_per_question": 1,
        "queries": {
            name: {
                "samples": len(values),
                "p50_ms": round(statistics.median(values), 2),
                "p95_ms": round(_percentile(values, 0.95), 2),
            }
            for name, values in samples.items()
        },
        "percentiles": {
            "samples": len(combined),
            "p50_ms": round(statistics.median(combined), 2),
            "p95_ms": round(_percentile(combined, 0.95), 2),
        },
        "limitations": [
            "Measured on the local judge-demo machine; network and hardware affect latency.",
            "This measures database query latency, not browser rendering or full HTTP response latency.",
        ],
    }
    RESULTS.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"Judge query latency p50={payload['percentiles']['p50_ms']} ms "
        f"p95={payload['percentiles']['p95_ms']} ms"
    )
    print(f"Wrote {RESULTS}")
    return 0


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * quantile) - 1)
    return ordered[index]


if __name__ == "__main__":
    raise SystemExit(main())
