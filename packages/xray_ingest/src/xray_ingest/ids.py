from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from xray_core.models import MAX_HYDRA_ID

type IdFactory = Callable[[str, str, str], int]


class IdCollisionError(ValueError):
    """Raised when one Hydra ID resolves to more than one canonical identity."""


@dataclass(frozen=True, slots=True)
class CanonicalIdentity:
    dataset_id: str
    label: str
    canonical_key: str


def _require_identity_part(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value


def _require_hydra_id(value: int) -> int:
    if type(value) is not int or not 1 <= value <= MAX_HYDRA_ID:
        raise ValueError("node_id must be a positive signed 63-bit integer")
    return value


def stable_id(dataset_id: str, label: str, canonical_key: str) -> int:
    dataset_id = _require_identity_part(dataset_id, "dataset_id")
    label = _require_identity_part(label, "label")
    canonical_key = _require_identity_part(canonical_key, "canonical_key")
    payload = f"{dataset_id}|{label}|{canonical_key}".encode()
    digest = hashlib.blake2b(payload, digest_size=8, person=b"xray-id").digest()
    value = int.from_bytes(digest, "big") & MAX_HYDRA_ID
    return value or 1


def stable_edge_id(
    dataset_id: str,
    rel_type: str,
    source_id: int,
    target_id: int,
    semantic_discriminator: str,
    *,
    id_factory: IdFactory = stable_id,
) -> int:
    _require_hydra_id(source_id)
    _require_hydra_id(target_id)
    discriminator = _require_identity_part(semantic_discriminator, "semantic_discriminator")
    return _require_hydra_id(
        id_factory(dataset_id, rel_type, f"{source_id}|{target_id}|{discriminator}")
    )


def path_key(label: str, node_id: int) -> str:
    normalized_label = _require_identity_part(label, "label").lower()
    if not normalized_label.isascii() or not normalized_label.isalpha():
        raise ValueError("label must contain only ASCII letters")
    return f"{normalized_label}:{_require_hydra_id(node_id):020d}"


class IdRegistry:
    """Fail-closed registry for deterministic node and relationship identities."""

    def __init__(self, id_factory: IdFactory = stable_id) -> None:
        self._id_factory = id_factory
        self._by_id: dict[int, CanonicalIdentity] = {}
        self._by_identity: dict[CanonicalIdentity, int] = {}

    def register(
        self,
        dataset_id: str,
        label: str,
        canonical_key: str,
        *,
        identity_id: int | None = None,
    ) -> int:
        identity = CanonicalIdentity(
            dataset_id=_require_identity_part(dataset_id, "dataset_id"),
            label=_require_identity_part(label, "label"),
            canonical_key=_require_identity_part(canonical_key, "canonical_key"),
        )
        resolved_id = (
            self._id_factory(dataset_id, label, canonical_key)
            if identity_id is None
            else identity_id
        )
        _require_hydra_id(resolved_id)

        registered_id = self._by_identity.get(identity)
        if registered_id is not None:
            if registered_id != resolved_id:
                raise IdCollisionError(
                    f"Identity {identity!r} changed from ID {registered_id} to {resolved_id}"
                )
            return registered_id

        registered_identity = self._by_id.get(resolved_id)
        if registered_identity is not None and registered_identity != identity:
            raise IdCollisionError(
                f"ID collision for {resolved_id}: {registered_identity!r} and {identity!r}"
            )

        self._by_id[resolved_id] = identity
        self._by_identity[identity] = resolved_id
        return resolved_id

    def identity_for(self, identity_id: int) -> CanonicalIdentity | None:
        return self._by_id.get(_require_hydra_id(identity_id))

    def __len__(self) -> int:
        return len(self._by_id)


__all__ = [
    "CanonicalIdentity",
    "IdCollisionError",
    "IdRegistry",
    "path_key",
    "stable_edge_id",
    "stable_id",
]
