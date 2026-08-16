from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path


def jira_csv_rows(
    path: Path,
    *,
    key_field: str = "key",
    created_field: str = "created",
    reporter_field: str = "reporter_id",
    module_field: str = "components",
) -> tuple[dict[str, object], ...]:
    """Convert a JIRA-style CSV export into rows accepted by ``ticket_records``."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return tuple(
            {
                "id": _required(row, key_field),
                "occurred_at_epoch": _epoch(_required(row, created_field)),
                "reporter_id": _required(row, reporter_field),
                "title": row.get("summary") or row.get("title") or "",
                "body": row.get("description") or "",
                "module_keys": _split_modules(row.get(module_field, "")),
            }
            for row in reader
        )


def _required(row: dict[str, str], field: str) -> str:
    value = row.get(field, "").strip()
    if not value:
        raise ValueError(f"JIRA CSV field {field!r} is required")
    return value


def _split_modules(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(
        sorted(item.strip() for item in value.replace(";", ",").split(",") if item.strip())
    )


def _epoch(value: str) -> int:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d").replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())
