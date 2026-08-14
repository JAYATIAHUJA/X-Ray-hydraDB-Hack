from __future__ import annotations

import os

import pytest


@pytest.mark.integration
def test_hydradb_live_smoke_requires_runtime() -> None:
    if os.environ.get("XRAY_RUNTIME_ID") is None:
        pytest.skip("set XRAY_RUNTIME_ID after starting the HydraDB core stack")
