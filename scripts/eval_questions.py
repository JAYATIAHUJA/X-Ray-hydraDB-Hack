"""Evaluate the deterministic question surface against the labelled judge corpus."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xray_analytics import answer_ontology_question
from xray_api.dependencies import demo_bundle

DEFAULT_CORPUS = Path("data/eval/judge_questions.json")
DEFAULT_OUTPUT = Path("docs/results/question-eval.json")


def evaluate(corpus_path: Path) -> dict[str, Any]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    bundle = demo_bundle()
    evidence_ids = {record.evidence_id for record in bundle.evidence}
    results = []
    category_totals: Counter[str] = Counter()
    category_passed: Counter[str] = Counter()
    evidence_total = 0
    evidence_passed = 0

    for group_index, group in enumerate(corpus["groups"], start=1):
        for question_index, question in enumerate(group["questions"], start=1):
            category = group["category"]
            answer = answer_ontology_question(bundle, question)
            checks = {
                "status": answer.status == group["expected_status"],
                "answer_kind": answer.answer_kind == group["expected_answer_kind"],
                "person_keys": list(answer.person_keys) == group["expected_person_keys"],
                "minimum_evidence": len(answer.evidence_ids) >= group["minimum_evidence"],
                "evidence_ids_exist": set(answer.evidence_ids) <= evidence_ids,
                "minimum_paths": len(answer.paths) >= group.get("minimum_paths", 0),
                "minimum_conflicts": len(answer.conflicts) >= group.get("minimum_conflicts", 0),
            }
            passed = all(checks.values())
            category_totals[category] += 1
            category_passed[category] += int(passed)
            if group["minimum_evidence"] > 0:
                evidence_total += 1
                evidence_passed += int(
                    checks["minimum_evidence"] and checks["evidence_ids_exist"]
                )
            results.append(
                {
                    "id": f"{category}-{group_index:02d}-{question_index:02d}",
                    "category": category,
                    "question": question,
                    "passed": passed,
                    "checks": checks,
                    "actual": {
                        "status": answer.status,
                        "answer_kind": answer.answer_kind,
                        "person_keys": list(answer.person_keys),
                        "evidence_count": len(answer.evidence_ids),
                        "path_count": len(answer.paths),
                        "conflict_count": len(answer.conflicts),
                    },
                }
            )

    total = len(results)
    passed = sum(item["passed"] for item in results)
    latency = _latency_status(Path("docs/results/judge-latency.json"))
    return {
        "dataset_id": corpus["dataset_id"],
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "method": "Exact labelled expectations over deterministic typed-edge answers; no LLM judge.",
        "corpus": {
            "path": str(corpus_path).replace("\\", "/"),
            "questions": total,
            "category_counts": dict(sorted(category_totals.items())),
        },
        "metrics": {
            "answer_accuracy": _metric(passed, total),
            "evidence_citation_accuracy": _metric(evidence_passed, evidence_total),
            "direct_answer_accuracy": _category_metric("direct", category_passed, category_totals),
            "multi_hop_accuracy": _category_metric("multi_hop", category_passed, category_totals),
            "conflict_resolution_accuracy": _category_metric(
                "conflict", category_passed, category_totals
            ),
            "abstention_accuracy": _category_metric(
                "unanswerable", category_passed, category_totals
            ),
            "hydradb_latency": latency,
        },
        "limitations": [
            "The corpus is manually labelled but synthetic and concentrated on the bundled demo ontology.",
            "Question variants test deterministic intent coverage; they are not 75 independent business scenarios.",
            "Live HydraDB latency remains unreported until the engine benchmark produces non-null p50 and p95.",
        ],
        "results": results,
    }


def _metric(numerator: int, denominator: int) -> dict[str, int | float]:
    return {
        "passed": numerator,
        "total": denominator,
        "rate": round(numerator / denominator, 4) if denominator else 0.0,
    }


def _category_metric(
    category: str, passed: Counter[str], totals: Counter[str]
) -> dict[str, int | float]:
    return _metric(passed[category], totals[category])


def _latency_status(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"status": "not_measured", "p50_ms": None, "p95_ms": None}
    payload = json.loads(path.read_text(encoding="utf-8"))
    percentiles = payload.get("percentiles", {})
    p50 = percentiles.get("p50_ms")
    p95 = percentiles.get("p95_ms")
    return {
        "status": "measured" if p50 is not None and p95 is not None else "not_measured",
        "p50_ms": p50,
        "p95_ms": p95,
        "source": str(path).replace("\\", "/"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--json", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    payload = evaluate(Path(args.corpus))
    output = Path(args.json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    metric = payload["metrics"]["answer_accuracy"]
    print(f"Question evaluation: {metric['passed']}/{metric['total']} passed")
    print(f"HydraDB latency: {payload['metrics']['hydradb_latency']['status']}")
    print(f"Wrote {output}")
    return 0 if metric["passed"] == metric["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
