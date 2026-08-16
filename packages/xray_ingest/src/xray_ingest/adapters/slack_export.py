from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path


def slack_export_rows(
    export_dir: Path,
    *,
    module_keys_by_channel: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[dict[str, object], ...]:
    """Convert a Slack export directory into rows accepted by ``slack_records``.

    The adapter uses explicit Slack user IDs and explicit thread metadata. Module
    keys are optional channel-level metadata supplied by the caller.
    """
    channel_modules = module_keys_by_channel or {}
    parent_authors: dict[tuple[str, str], str] = {}
    messages: list[tuple[str, dict[str, object]]] = []
    for channel_dir in sorted(path for path in export_dir.iterdir() if path.is_dir()):
        channel = channel_dir.name
        for json_path in sorted(channel_dir.glob("*.json")):
            for message in json.loads(json_path.read_text(encoding="utf-8")):
                if not isinstance(message, dict) or not isinstance(message.get("user"), str):
                    continue
                timestamp = _required_str(message, "ts")
                parent_authors[(channel, timestamp)] = _required_str(message, "user")
                messages.append((channel, message))

    rows = []
    for channel, message in messages:
        timestamp = _required_str(message, "ts")
        thread_ts = message.get("thread_ts")
        parent_author_id = None
        if isinstance(thread_ts, str) and thread_ts != timestamp:
            parent_author_id = parent_authors.get((channel, thread_ts))
        rows.append(
            {
                "id": f"{channel}-{timestamp}",
                "occurred_at_epoch": int(float(timestamp)),
                "author_id": _required_str(message, "user"),
                "thread_parent_id": f"{channel}-{thread_ts}" if parent_author_id else None,
                "parent_author_id": parent_author_id,
                "mentions": _mentions(str(message.get("text", ""))),
                "module_keys": tuple(channel_modules.get(channel, ())),
                "text": message.get("text") if isinstance(message.get("text"), str) else None,
            }
        )
    return tuple(rows)


def _required_str(message: dict[str, object], key: str) -> str:
    value = message.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Slack message field {key!r} is required")
    return value.strip()


def _mentions(text: str) -> tuple[str, ...]:
    mentions = []
    for part in text.split("<@")[1:]:
        user_id = part.split(">", maxsplit=1)[0].split("|", maxsplit=1)[0]
        if user_id:
            mentions.append(user_id)
    return tuple(sorted(set(mentions)))
