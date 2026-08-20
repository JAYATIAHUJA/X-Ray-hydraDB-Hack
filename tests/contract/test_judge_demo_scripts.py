from __future__ import annotations

import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).parents[2]
verify_module = runpy.run_path(str(ROOT / "scripts" / "verify_judge_demo.py"))
verify = verify_module["verify"]


def test_judge_demo_verifier_requires_live_loaded_hydra() -> None:
    with patch.dict(
        verify.__globals__,
        {
            "_request": lambda *_args, **_kwargs: {
                "hydra": {"status": "fallback", "graph_loaded": False}
            }
        },
    ):
        with pytest.raises(RuntimeError, match="requires HydraDB live"):
            verify("http://demo")


def test_judge_demo_verifier_requires_query_proof() -> None:
    responses = iter(
        (
            {"hydra": {"status": "live", "graph_loaded": True}},
            {"snapshot_id": "demo"},
            {
                "source": "fixture",
                "executed_query": None,
                "degraded_reason": "engine unavailable",
            },
        )
    )
    with patch.dict(
        verify.__globals__,
        {"_request": lambda *_args, **_kwargs: next(responses)},
    ):
        with pytest.raises(RuntimeError, match="did not produce live HydraDB proof"):
            verify("http://demo")


def test_judge_demo_verifier_returns_three_live_proofs() -> None:
    answers = [
        {
            "status": status,
            "answer_kind": kind,
            "source": "hydradb",
            "engine_ms": 4.2,
            "round_trips": 1,
            "executed_query": {"text": "MATCH (n) RETURN n"},
            "degraded_reason": None,
        }
        for status, kind in (
            ("answered", "direct"),
            ("answered", "multi_hop"),
            ("no_answer", "abstention"),
        )
    ]
    responses = iter(
        (
            {"hydra": {"status": "live", "graph_loaded": True}},
            {"snapshot_id": "demo"},
            *answers,
        )
    )
    with patch.dict(
        verify.__globals__,
        {"_request": lambda *_args, **_kwargs: next(responses)},
    ):
        proof = verify("http://demo")

    assert len(proof["questions"]) == 3
    assert all(item["source"] == "hydradb" for item in proof["questions"])
