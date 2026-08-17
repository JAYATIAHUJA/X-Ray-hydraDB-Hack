from __future__ import annotations

import mailbox
from collections.abc import Mapping
from datetime import UTC
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path


def mbox_rows(
    path: Path,
    *,
    module_keys_by_message_id: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[dict[str, object], ...]:
    """Convert an mbox export into rows accepted by ``email_records``.

    People are identified by explicit email addresses in message headers. Module
    keys must be supplied out-of-band; this adapter does not infer modules from
    message text.
    """
    module_keys = module_keys_by_message_id or {}
    rows: list[dict[str, object]] = []
    for fallback_id, message in enumerate(mailbox.mbox(path)):
        message_id = _message_id(message) or str(fallback_id)
        sender = _first_address(message.get_all("from", ()))
        recipients = _addresses((*message.get_all("to", ()), *message.get_all("cc", ())))
        if sender is None or not recipients:
            continue
        epoch = _epoch(message)
        if epoch is None:
            # No parseable Date header: the message cannot be placed on the timeline
            # and would corrupt gap interpolation, so it is skipped rather than
            # silently stamped as 1970.
            continue
        rows.append(
            {
                "id": message_id,
                "occurred_at_epoch": epoch,
                "from_id": sender,
                "to_ids": recipients,
                "in_reply_to_id": _clean_message_id(message.get("In-Reply-To")),
                "subject": message.get("Subject"),
                "body": _plain_text(message),
                "module_keys": tuple(module_keys.get(message_id, ())),
            }
        )
    return tuple(rows)


def _message_id(message: Message) -> str | None:
    return _clean_message_id(message.get("Message-ID"))


def _clean_message_id(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().removeprefix("<").removesuffix(">")
    return cleaned or None


def _first_address(values: tuple[str, ...] | list[str]) -> str | None:
    addresses = _addresses(values)
    return addresses[0] if addresses else None


def _addresses(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                address.lower()
                for _name, address in getaddresses(values)
                if address and "@" in address
            }
        )
    )


def _epoch(message: Message) -> int | None:
    value = message.get("Date")
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        # RFC 5322 dates without a zone are treated as UTC so the epoch is the same
        # on every machine (local-time interpretation is not deterministic).
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def _plain_text(message: Message) -> str | None:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                return _payload_text(part)
        return None
    if message.get_content_type() != "text/plain":
        return None
    return _payload_text(message)


def _payload_text(message: Message) -> str | None:
    payload = message.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return None
    charset = message.get_content_charset() or "utf-8"
    text = payload.decode(charset, errors="replace").strip()
    return text or None
