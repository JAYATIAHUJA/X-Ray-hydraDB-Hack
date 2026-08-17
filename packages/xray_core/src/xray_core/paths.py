"""Helpers for working with HydraDB path rows and person pairs.

HydraDB path procedures return paths either as an alternating node/relationship
sequence or as an object exposing ``nodes``. These helpers normalize both shapes
into the node keys the analysis layer reasons about, without depending on the
Neo4j driver types.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def normalize_pair(left: str, right: str) -> tuple[str, str]:
    """Return an undirected pair in a canonical (sorted) order."""
    return (left, right) if left <= right else (right, left)


def node_value(node: object, key: str) -> object:
    """Read ``key`` from a path node that may be a mapping or a driver record."""
    if isinstance(node, Mapping):
        return node.get(key)
    try:
        return node[key]  # type: ignore[index]
    except Exception:
        return None


def path_nodes(path: object) -> tuple[object, ...]:
    """Extract the node entries from a HydraDB path value.

    Alternating ``[node, rel, node, ...]`` sequences are filtered to mapping-like
    entries; objects exposing ``nodes`` are unwrapped. Returns ``()`` when the
    shape is not recognized.
    """
    if path is None:
        return ()
    if isinstance(path, (list, tuple)):
        return tuple(
            item
            for item in path
            if isinstance(item, Mapping)
            or (not isinstance(item, str) and hasattr(item, "__getitem__"))
        )
    raw_nodes = path.get("nodes") if isinstance(path, Mapping) else getattr(path, "nodes", None)
    if not isinstance(raw_nodes, (list, tuple)):
        return ()
    return tuple(raw_nodes)


def path_key_tuple(
    path: object,
    *,
    keys: Sequence[str] = ("canonical_key", "path_key"),
) -> tuple[str, ...]:
    """Return the identifying key of every node on a path, or ``()`` if any is missing.

    ``keys`` lists the node properties to try in order (the first string value wins).
    """
    result: list[str] = []
    for node in path_nodes(path):
        value: object = None
        for key in keys:
            value = node_value(node, key)
            if isinstance(value, str):
                break
        if not isinstance(value, str):
            return ()
        result.append(value)
    return tuple(result)


__all__ = ["node_value", "normalize_pair", "path_key_tuple", "path_nodes"]
