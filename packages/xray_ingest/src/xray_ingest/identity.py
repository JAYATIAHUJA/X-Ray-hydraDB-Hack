"""Offline identity resolution for export rows.

Real exports identify people by source-native ids (email addresses, Slack user ids,
JIRA account ids). The graph must only ever see one stable handle per person, so
this module rewrites those ids **before** canonicalization using an explicit,
caller-supplied map. It is deterministic and never fuzzy: an id is either mapped,
or it is kept as an *unresolved* handle with a directory stub and a limitation
note so the pipeline degrades visibly instead of raising.

Nothing here touches HydraDB. All resolution happens in the loader, in Python.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from xray_core.models import CanonicalRecord

# Person-id fields per export row shape, as consumed by ``xray_ingest.sources``.
IDENTITY_FIELDS: Mapping[str, tuple[str, ...]] = {
    "slack": ("author_id", "parent_author_id", "mentions"),
    "email": ("from_id", "to_ids"),
    "ticket": ("reporter_id",),
    "git": ("author_id",),
}

_HANDLE_SAFE = re.compile(r"[^a-z0-9._-]+")


@dataclass
class IdentityResolution:
    """Outcome of resolving one export bundle."""

    resolved: dict[str, str] = field(default_factory=dict)
    unresolved: dict[str, str] = field(default_factory=dict)  # raw id -> synthesized handle

    @property
    def limitations(self) -> tuple[str, ...]:
        if not self.unresolved:
            return ()
        sample = ", ".join(sorted(self.unresolved)[:5])
        more = "" if len(self.unresolved) <= 5 else f" (+{len(self.unresolved) - 5} more)"
        return (
            f"{len(self.unresolved)} source identities were not in the identity map and were "
            f"kept as unresolved handles: {sample}{more}. Ghost and Faultline results for those "
            "people are per-source-id, not per-person.",
        )


def normalize_source_id(value: str) -> str:
    """Case-fold and trim a source id; strips mailto: and angle brackets."""
    cleaned = value.strip().removeprefix("mailto:").strip("<>").strip().lower()
    return cleaned


def unresolved_handle(source_id: str) -> str:
    """Deterministic, URL-safe handle for a source id with no directory entry."""
    digest = hashlib.blake2b(source_id.encode("utf-8"), digest_size=4).hexdigest()
    local = source_id.split("@", 1)[0] if "@" in source_id else source_id
    stem = _HANDLE_SAFE.sub("-", local.lower()).strip("-")[:24] or "id"
    return f"unresolved-{stem}-{digest}"


def resolve_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    kind: str,
    identity_map: Mapping[str, str],
    resolution: IdentityResolution,
) -> tuple[dict[str, object], ...]:
    """Return copies of ``rows`` with person-id fields mapped through ``identity_map``.

    ``identity_map`` keys are normalized source ids (lower-cased email addresses,
    Slack user ids, …) and values are directory handles (e.g. ``priya-nair``).
    """
    fields = IDENTITY_FIELDS.get(kind)
    if fields is None:
        raise ValueError(f"unknown export kind {kind!r}")
    lowered = {normalize_source_id(key): value for key, value in identity_map.items()}
    resolved_rows: list[dict[str, object]] = []
    for row in rows:
        updated = dict(row)
        for name in fields:
            value = updated.get(name)
            if value is None:
                continue
            if isinstance(value, str):
                updated[name] = _resolve_one(value, lowered, resolution)
            elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
                updated[name] = tuple(
                    _resolve_one(item, lowered, resolution)
                    for item in value
                    if isinstance(item, str)
                )
        resolved_rows.append(updated)
    return tuple(resolved_rows)


def _resolve_one(raw: str, identity_map: Mapping[str, str], resolution: IdentityResolution) -> str:
    key = normalize_source_id(raw)
    handle = identity_map.get(key)
    if handle is not None:
        resolution.resolved[key] = handle
        return handle
    if key in resolution.unresolved:
        return resolution.unresolved[key]
    if key in identity_map.values():
        # Already a handle (e.g. fixture rows that use handles directly).
        return key
    synthesized = unresolved_handle(key)
    resolution.unresolved[key] = synthesized
    return synthesized


def unresolved_directory_records(
    resolution: IdentityResolution,
    *,
    source: str,
    epoch: int,
    known_handles: Iterable[str],
) -> tuple[CanonicalRecord, ...]:
    """Directory stubs for synthesized handles so derivation never hits a missing endpoint."""
    known = set(known_handles)
    records = []
    for raw_id, handle in sorted(resolution.unresolved.items()):
        if handle in known:
            continue
        records.append(
            CanonicalRecord(
                source=source,
                external_id=handle,
                kind="directory_person",
                occurred_at_epoch=epoch,
                author_external_id=None,
                parent_external_id=None,
                subjects=(f"person:{handle}",),
                content_sha256=hashlib.sha256(b"").hexdigest(),
                content=None,
                metadata={
                    "display_name": raw_id,
                    "role_rank": 0,
                    "identity_status": "unresolved",
                    "source_identity": raw_id,
                },
            )
        )
    return tuple(records)


__all__ = [
    "IDENTITY_FIELDS",
    "IdentityResolution",
    "normalize_source_id",
    "resolve_rows",
    "unresolved_directory_records",
    "unresolved_handle",
]
