"""FastAPI composition root.

Route registration and response assembly live in :mod:`xray_api.routes`; this
module stays intentionally small so deployment imports have one stable target.
"""

from .routers import api as _routes

app = _routes.app
create_app = _routes.create_app

# Compatibility aliases for focused unit tests and downstream diagnostic imports.
_window_bundle = _routes._window_bundle
_with_gap_evidence = _routes._with_gap_evidence
_with_live_distance = _routes._with_live_distance

__all__ = ["app", "create_app"]
