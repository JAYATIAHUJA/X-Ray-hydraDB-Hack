from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).parents[2]
evaluate = runpy.run_path(str(ROOT / "scripts" / "eval_questions.py"))["evaluate"]


def test_labelled_question_eval_has_requested_category_sizes_and_passes() -> None:
    result = evaluate(ROOT / "data" / "eval" / "judge_questions.json")

    assert result["corpus"]["questions"] == 75
    assert result["corpus"]["category_counts"] == {
        "conflict": 15,
        "direct": 25,
        "multi_hop": 20,
        "unanswerable": 15,
    }
    assert result["metrics"]["answer_accuracy"] == {
        "passed": 75,
        "total": 75,
        "rate": 1.0,
    }
    latency = result["metrics"]["hydradb_latency"]
    assert latency["status"] == "measured"
    assert latency["p50_ms"] > 0
    assert latency["p95_ms"] >= latency["p50_ms"]
