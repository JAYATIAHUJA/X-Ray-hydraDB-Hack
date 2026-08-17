"""Deterministic JSON serialization shared by ingest, hashing, and fixtures."""

from __future__ import annotations

import json


def canonical_json(value: object) -> str:
    """Serialize ``value`` with sorted keys, compact separators, and no NaN/Infinity.

    Every content hash in X-Ray is computed over this representation so that the
    same logical record always yields the same digest across processes and platforms.
    """
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = ["canonical_json"]
