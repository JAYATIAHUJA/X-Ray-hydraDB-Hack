"""Fail closed unless the running API proves a seeded, live HydraDB question path."""

from __future__ import annotations

import argparse
import json
import urllib.request
from typing import Any


def _request(url: str, payload: dict[str, object] | None = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def verify(api_base: str) -> dict[str, object]:
    health = _request(f"{api_base}/api/v1/health")
    hydra = health["hydra"]
    if hydra["status"] != "live" or not hydra["graph_loaded"]:
        raise RuntimeError(
            "Judge demo requires HydraDB live with a loaded graph; "
            f"received status={hydra['status']!r}, graph_loaded={hydra['graph_loaded']!r}."
        )
    snapshot = _request(f"{api_base}/api/v1/snapshots/current")
    questions = (
        "Who owns payments-api now, and why did an older Jira record say Alex?",
        "Which services are affected if ledger-worker changes?",
        "Who approved the refund limit change?",
    )
    proofs = []
    for question in questions:
        answer = _request(
            f"{api_base}/api/v1/snapshots/{snapshot['snapshot_id']}/questions",
            {"question": question},
        )
        if answer["source"] != "hydradb" or answer["executed_query"] is None:
            raise RuntimeError(
                f"Question did not produce live HydraDB proof: {question!r}. "
                f"source={answer['source']!r}, degraded_reason={answer['degraded_reason']!r}"
            )
        proofs.append(
            {
                "question": question,
                "status": answer["status"],
                "answer_kind": answer["answer_kind"],
                "source": answer["source"],
                "engine_ms": answer["engine_ms"],
                "round_trips": answer["round_trips"],
                "query": answer["executed_query"]["text"],
            }
        )
    return {
        "hydra": hydra,
        "snapshot": snapshot,
        "questions": proofs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    proof = verify(args.api_base.rstrip("/"))
    print(json.dumps(proof, indent=2))
    print("Judge demo verification passed: live HydraDB, loaded graph, and query proof confirmed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
