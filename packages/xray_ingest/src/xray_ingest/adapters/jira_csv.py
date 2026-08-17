from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

# Real JIRA CSV exports ("Issue key", "Created", …) and the simpler test/synthetic
# shape ("key", "created", …) are both accepted; the first present column wins.
KEY_FIELDS: tuple[str, ...] = ("Issue key", "key", "Key")
CREATED_FIELDS: tuple[str, ...] = ("Created", "created")
REPORTER_FIELDS: tuple[str, ...] = ("Reporter", "reporter_id", "reporter")
SUMMARY_FIELDS: tuple[str, ...] = ("Summary", "summary", "title")
DESCRIPTION_FIELDS: tuple[str, ...] = ("Description", "description")
MODULE_FIELDS: tuple[str, ...] = ("Component/s", "components", "Components")

# Date formats JIRA emits, in order of likelihood. ISO-8601 is tried first.
JIRA_DATE_FORMATS: tuple[str, ...] = (
    "%d/%b/%y %I:%M %p",  # 30/Jun/25 11:47 PM
    "%d/%b/%y %H:%M",  # 30/Jun/25 23:47
    "%d/%b/%Y %I:%M %p",
    "%d/%b/%Y %H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def jira_csv_rows(
    path: Path,
    *,
    key_field: str | Sequence[str] = KEY_FIELDS,
    created_field: str | Sequence[str] = CREATED_FIELDS,
    reporter_field: str | Sequence[str] = REPORTER_FIELDS,
    module_field: str | Sequence[str] = MODULE_FIELDS,
) -> tuple[dict[str, object], ...]:
    """Convert a JIRA CSV export into rows accepted by ``ticket_records``.

    Reporter usernames are passed through unchanged; map them to directory handles
    with the identity map. Multiple ``Component/s`` columns (JIRA repeats the header
    per value) are merged.
    """
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            return ()
        rows: list[dict[str, object]] = []
        for values in reader:
            if not any(cell.strip() for cell in values):
                continue
            record = _row_map(header, values)
            key = _first(record, key_field, required=True)
            rows.append(
                {
                    "id": key,
                    "occurred_at_epoch": _epoch(_first(record, created_field, required=True)),
                    "reporter_id": _first(record, reporter_field, required=True),
                    "title": _first(record, SUMMARY_FIELDS) or None,
                    "body": _first(record, DESCRIPTION_FIELDS) or None,
                    "module_keys": _split_modules(_all(record, module_field)),
                }
            )
        return tuple(rows)


def _row_map(header: list[str], values: list[str]) -> dict[str, list[str]]:
    """Group cell values by column name so repeated JIRA columns are not lost."""
    grouped: dict[str, list[str]] = {}
    for name, value in zip(header, values, strict=False):
        grouped.setdefault(name.strip(), []).append(value)
    return grouped


def _first(
    record: dict[str, list[str]], fields: str | Sequence[str], *, required: bool = False
) -> str:
    names = (fields,) if isinstance(fields, str) else tuple(fields)
    for name in names:
        for value in record.get(name, ()):
            if value and value.strip():
                return value.strip()
    if required:
        raise ValueError(f"JIRA CSV field {names[0]!r} is required")
    return ""


def _all(record: dict[str, list[str]], fields: str | Sequence[str]) -> str:
    names = (fields,) if isinstance(fields, str) else tuple(fields)
    values = [value.strip() for name in names for value in record.get(name, ()) if value.strip()]
    return ",".join(values)


def _split_modules(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(
        sorted({item.strip() for item in value.replace(";", ",").split(",") if item.strip()})
    )


def _epoch(value: str) -> int:
    parsed = _parse_date(value.strip())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def _parse_date(text: str) -> datetime:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in JIRA_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"unrecognised JIRA date {text!r}")
