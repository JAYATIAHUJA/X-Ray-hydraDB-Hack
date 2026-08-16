"""Deterministic adapters for the first supported X-Ray source exports.

These adapters deliberately do not guess people, modules, or reply targets from
message text. Callers must supply resolved external IDs and explicit module
references; that keeps fuzzy extraction outside the graph loading boundary.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from itertools import combinations
from typing import Literal

from xray_core.models import CanonicalRecord


class SourceAdapterError(ValueError):
    """Raised when a source export omits a fact needed for deterministic ingestion."""


RawRecord = Mapping[str, object]


def _required_string(record: RawRecord, field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SourceAdapterError(f"{field} must be a non-empty string")
    return value.strip()


def _required_epoch(record: RawRecord, field: str) -> int:
    value = record.get(field)
    if type(value) is not int or value < 0:
        raise SourceAdapterError(f"{field} must be a non-negative integer epoch")
    return value


def _optional_string(record: RawRecord, field: str) -> str | None:
    value = record.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SourceAdapterError(f"{field} must be a non-empty string when present")
    return value.strip()


def _string_list(record: RawRecord, field: str) -> tuple[str, ...]:
    value = record.get(field, ())
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise SourceAdapterError(f"{field} must be a list of non-empty strings")
    return tuple(sorted(set(item.strip() for item in value)))


def _module_subjects(record: RawRecord) -> tuple[str, ...]:
    return tuple(
        f"module:{key.removeprefix('module:')}" for key in _string_list(record, "module_keys")
    )


def _content_hash(*parts: str | None) -> str:
    payload = "\n".join(part or "" for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _artifact(
    *,
    source: str,
    external_id: str,
    epoch: int,
    author_id: str,
    parent_id: str | None,
    content: str | None,
    artifact_kind: str,
    module_subjects: tuple[str, ...],
) -> CanonicalRecord:
    artifact_key = f"artifact:{source}:{external_id}"
    return CanonicalRecord(
        source=source,
        external_id=f"{source}:{external_id}",
        kind="artifact",
        occurred_at_epoch=epoch,
        author_external_id=author_id,
        parent_external_id=parent_id,
        subjects=(artifact_key, *module_subjects),
        content_sha256=_content_hash(content),
        content=content,
        metadata={"artifact_kind": artifact_kind, "canonical_key": artifact_key},
    )


def _communication(
    *,
    source: str,
    external_id: str,
    epoch: int,
    sender_id: str,
    recipient_id: str,
    kind: Literal["mention", "reply", "email"],
) -> CanonicalRecord:
    return CanonicalRecord(
        source=source,
        external_id=f"{source}:{external_id}:communication:{recipient_id}",
        kind="communication_aggregate",
        occurred_at_epoch=epoch,
        author_external_id=sender_id,
        parent_external_id=None,
        subjects=(f"person:{sender_id}", f"person:{recipient_id}"),
        content_sha256=_content_hash(source, external_id, sender_id, recipient_id, kind),
        content=None,
        metadata={
            "first_epoch": epoch,
            "interaction_count": 1,
            "interaction_kind": kind,
            "last_epoch": epoch,
            "recipient_external_id": recipient_id,
            "sender_external_id": sender_id,
        },
    )


def _dependency(
    *,
    source: str,
    external_id: str,
    epoch: int,
    source_module: str,
    target_module: str,
    weight: int,
) -> CanonicalRecord:
    source_key = f"module:{source_module.removeprefix('module:')}"
    target_key = f"module:{target_module.removeprefix('module:')}"
    return CanonicalRecord(
        source=source,
        external_id=f"{source}:{external_id}:dependency:{target_module}",
        kind="dependency",
        occurred_at_epoch=epoch,
        author_external_id=None,
        parent_external_id=None,
        subjects=(source_key, target_key),
        content_sha256=_content_hash(source, external_id, source_key, target_key),
        content=None,
        metadata={
            "dependency_kind": "explicit_reference",
            "source_module_external_id": source_key.removeprefix("module:"),
            "target_module_external_id": target_key.removeprefix("module:"),
            "weight": weight,
        },
    )


def _cochange(
    *,
    source: str,
    external_id: str,
    epoch: int,
    source_module: str,
    target_module: str,
) -> CanonicalRecord:
    source_key = f"module:{source_module.removeprefix('module:')}"
    target_key = f"module:{target_module.removeprefix('module:')}"
    return CanonicalRecord(
        source=source,
        external_id=f"{source}:{external_id}:cochange:{source_key}:{target_key}",
        kind="cochange",
        occurred_at_epoch=epoch,
        author_external_id=None,
        parent_external_id=None,
        subjects=(source_key, target_key),
        content_sha256=_content_hash(source, external_id, source_key, target_key),
        content=None,
        metadata={
            "cochange_count": 1,
            "relationship_class": "inferred_coupling",
            "source_module_external_id": source_key.removeprefix("module:"),
            "target_module_external_id": target_key.removeprefix("module:"),
        },
    )


def slack_records(rows: Iterable[RawRecord]) -> tuple[CanonicalRecord, ...]:
    """Normalize Slack messages with explicit mentions or a resolved reply author.

    Required fields: ``id``, ``occurred_at_epoch``, ``author_id``. Optional
    fields: ``text``, ``thread_parent_id``, ``parent_author_id``, ``mentions``,
    and ``module_keys``.
    """
    records: list[CanonicalRecord] = []
    for row in rows:
        external_id = _required_string(row, "id")
        epoch = _required_epoch(row, "occurred_at_epoch")
        author_id = _required_string(row, "author_id")
        parent_id = _optional_string(row, "thread_parent_id")
        text = _optional_string(row, "text")
        records.append(
            _artifact(
                source="slack",
                external_id=external_id,
                epoch=epoch,
                author_id=author_id,
                parent_id=parent_id,
                content=text,
                artifact_kind="message",
                module_subjects=_module_subjects(row),
            )
        )
        parent_author = _optional_string(row, "parent_author_id")
        if parent_author is not None and parent_author != author_id:
            records.append(
                _communication(
                    source="slack",
                    external_id=external_id,
                    epoch=epoch,
                    sender_id=author_id,
                    recipient_id=parent_author,
                    kind="reply",
                )
            )
        for recipient_id in _string_list(row, "mentions"):
            if recipient_id != author_id:
                records.append(
                    _communication(
                        source="slack",
                        external_id=external_id,
                        epoch=epoch,
                        sender_id=author_id,
                        recipient_id=recipient_id,
                        kind="mention",
                    )
                )
    return tuple(records)


def email_records(rows: Iterable[RawRecord]) -> tuple[CanonicalRecord, ...]:
    """Normalize email with explicit sender, recipients, and optional module references."""
    records: list[CanonicalRecord] = []
    for row in rows:
        external_id = _required_string(row, "id")
        epoch = _required_epoch(row, "occurred_at_epoch")
        sender_id = _required_string(row, "from_id")
        recipients = _string_list(row, "to_ids")
        subject = _optional_string(row, "subject")
        body = _optional_string(row, "body")
        content = "\n\n".join(part for part in (subject, body) if part) or None
        records.append(
            _artifact(
                source="email",
                external_id=external_id,
                epoch=epoch,
                author_id=sender_id,
                parent_id=_optional_string(row, "in_reply_to_id"),
                content=content,
                artifact_kind="email",
                module_subjects=_module_subjects(row),
            )
        )
        for recipient_id in recipients:
            if recipient_id != sender_id:
                records.append(
                    _communication(
                        source="email",
                        external_id=external_id,
                        epoch=epoch,
                        sender_id=sender_id,
                        recipient_id=recipient_id,
                        kind="email",
                    )
                )
    return tuple(records)


def ticket_records(rows: Iterable[RawRecord]) -> tuple[CanonicalRecord, ...]:
    """Normalize ticket exports without inferring ownership from an assignee field."""
    return tuple(
        _artifact(
            source="ticket",
            external_id=_required_string(row, "id"),
            epoch=_required_epoch(row, "occurred_at_epoch"),
            author_id=_required_string(row, "reporter_id"),
            parent_id=None,
            content="\n\n".join(
                part
                for part in (_optional_string(row, "title"), _optional_string(row, "body"))
                if part
            )
            or None,
            artifact_kind="ticket",
            module_subjects=_module_subjects(row),
        )
        for row in rows
    )


def code_records(rows: Iterable[RawRecord]) -> tuple[CanonicalRecord, ...]:
    """Normalize commits and their explicitly declared module dependencies."""
    records: list[CanonicalRecord] = []
    for row in rows:
        external_id = _required_string(row, "sha")
        epoch = _required_epoch(row, "occurred_at_epoch")
        author_id = _required_string(row, "author_id")
        records.append(
            _artifact(
                source="git",
                external_id=external_id,
                epoch=epoch,
                author_id=author_id,
                parent_id=None,
                content=_optional_string(row, "message"),
                artifact_kind="commit",
                module_subjects=_module_subjects(row),
            )
        )
        source_modules = _string_list(row, "module_keys")
        for source_module, target_module in combinations(source_modules, 2):
            records.append(
                _cochange(
                    source="git",
                    external_id=external_id,
                    epoch=epoch,
                    source_module=source_module,
                    target_module=target_module,
                )
            )
        dependency_keys = _string_list(row, "dependency_keys")
        for source_module in source_modules:
            for target_module in dependency_keys:
                records.append(
                    _dependency(
                        source="git",
                        external_id=external_id,
                        epoch=epoch,
                        source_module=source_module,
                        target_module=target_module,
                        weight=1,
                    )
                )
    return tuple(records)


__all__ = [
    "SourceAdapterError",
    "code_records",
    "email_records",
    "slack_records",
    "ticket_records",
]
