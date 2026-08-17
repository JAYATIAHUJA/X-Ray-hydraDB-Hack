from __future__ import annotations

import subprocess
import sys


def test_eval_synth_reports_planted_metrics() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/eval_synth.py", "--sample-pairs", "500"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "| Faultline precision | 1.000 |" in result.stdout
    assert "| Faultline recall | 1.000 |" in result.stdout
    assert "| Gap recall | 1.000 |" in result.stdout
    assert "| Gap precision | 1.000 |" in result.stdout
    assert "Ghost top-1 hit rate across seeds" in result.stdout
