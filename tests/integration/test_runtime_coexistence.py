from __future__ import annotations

import os

import pytest


@pytest.mark.integration
def test_runtime_coexistence_requires_two_live_runtimes() -> None:
    if os.environ.get("XRAY_OLD_RUNTIME_ID") is None or os.environ.get("XRAY_GREEN_RUNTIME_ID") is None:
        pytest.skip("set XRAY_OLD_RUNTIME_ID and XRAY_GREEN_RUNTIME_ID for live coexistence")
