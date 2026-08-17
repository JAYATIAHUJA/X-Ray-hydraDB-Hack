from __future__ import annotations

import mailbox
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path


def mbox_rows(
    path: Path | Sequence[Path],
    *,
    module_keys_by_message_id: Mapping[str, tuple[str, ...]] | None = None,
    ignore_addresses: Iterable[str] = (),
    skip_senders: Iterable[str] = (),
) -> tuple[dict[str, object], ...]:
    """Convert one or more mbox exports into rows accepted by ``email_records``.

    People are identified by explicit email addresses in message headers. Module
    keys must be supplied out-of-band; this adapter does not infer modules from
    message text.

    * ``ignore_addresses`` — recipient addresses that are not people (mailing-list
      addresses such as ``dev@project.apache.org``). They are dropped from
      ``to_ids`` so they never become Person nodes.
    * ``skip_senders`` — automated senders (JIRA/Jenkins/git relays) whose messages
      are excluded entirely; they would otherwise become artificial hubs.
    * ``parent_author_id`` — when ``In-Reply-To`` names a message inside the same
      export, the parent's sender is attached so a reply becomes a person-to-person
      communication edge (the same signal Slack threads carry). Dangling parents
      are kept as ``in_reply_to_id`` so the Gaps lens can materialise them.
    """
    module_keys = module_keys_by_message_id or {}
    ignored = {address.lower() for address in ignore_addresses}
    skipped = {address.lower() for address in skip_senders}
    paths = [path] if isinstance(path, Path) else list(path)

    parsed: list[tuple[str, Message]] = []
    for mbox_path in paths:
        for fallback_id, mbox_message in enumerate(mailbox.mbox(mbox_path)):
            message: Message = mbox_message
            message_id = _message_id(message) or f"{mbox_path.name}:{fallback_id}"
            parsed.append((message_id, message))
    sender_by_message_id: dict[str, str] = {}
    for message_id, message in parsed:
        sender = _first_address(message.get_all("from", ()))
        if sender is not None:
            sender_by_message_id[message_id] = sender

    rows: list[dict[str, object]] = []
    for message_id, message in parsed:
        sender = _first_address(message.get_all("from", ()))
        if sender is None or sender in skipped:
            continue
        recipients = tuple(
            address
            for address in _addresses((*message.get_all("to", ()), *message.get_all("cc", ())))
            if address not in ignored
        )
        in_reply_to = _clean_message_id(message.get("In-Reply-To"))
        parent_author = sender_by_message_id.get(in_reply_to) if in_reply_to else None
        if not recipients and parent_author is None and in_reply_to is None:
            # Broadcast to a list with no thread context: no person-to-person signal.
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
                "in_reply_to_id": in_reply_to,
                "parent_author_id": parent_author,
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
