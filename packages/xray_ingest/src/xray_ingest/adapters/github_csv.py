from __future__ import annotations

import csv
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

_log = logging.getLogger(__name__)

NUMBER_FIELDS: tuple[str, ...] = ("number", "Number", "issue_number")
TITLE_FIELDS: tuple[str, ...] = ("title", "Title")
BODY_FIELDS: tuple[str, ...] = ("body", "Body")
CREATED_FIELDS: tuple[str, ...] = ("created_at", "Created At", "created")
USER_FIELDS: tuple[str, ...] = ("user", "User", "author", "Author")
LABELS_FIELDS: tuple[str, ...] = ("labels", "Labels")


def github_csv_rows(
    path: Path,
    *,
    repo_module: str | None = None,
    label_modules: Mapping[str, str] | None = None,
) -> tuple[dict[str, object], ...]:
    """Convert a GitHub Issues CSV export into rows accepted by ``ticket_records``.

    ``repo_module`` is always added to every row's ``module_keys`` when set.
    ``label_modules`` maps label strings to module keys (e.g. ``{"payments": "payments-api"}``).
    Column names are normalised; see ``NUMBER_FIELDS`` / ``USER_FIELDS`` / ``CREATED_FIELDS``.
    """
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return ()
        col = _column_map(list(reader.fieldnames))
        rows: list[dict[str, object]] = []
        for raw in reader:
            if not any(v.strip() for v in raw.values()):
                continue
            row = _parse_row(raw, col, repo_module, label_modules or {})
            if row is not None:
                rows.append(row)
    rows.sort(key=lambda r: int(str(r["occurred_at_epoch"])))
    return tuple(rows)


def _column_map(fieldnames: list[str]) -> dict[str, str]:
    """Return a mapping from canonical name → actual CSV header for known aliases."""
    mapping: dict[str, str] = {}
    groups = {
        "number": NUMBER_FIELDS,
        "title": TITLE_FIELDS,
        "body": BODY_FIELDS,
        "created_at": CREATED_FIELDS,
        "user": USER_FIELDS,
        "labels": LABELS_FIELDS,
    }
    for canonical, candidates in groups.items():
        for candidate in candidates:
            if candidate in fieldnames:
                mapping[canonical] = candidate
                break
    return mapping


def _parse_row(
    raw: dict[str, str],
    col: dict[str, str],
    repo_module: str | None,
    label_modules: Mapping[str, str],
) -> dict[str, object] | None:
    number_col = col.get("number")
    created_col = col.get("created_at")
    user_col = col.get("user")

    if number_col is None or created_col is None or user_col is None:
        return None

    number = raw.get(number_col, "").strip()
    created = raw.get(created_col, "").strip()
    user = raw.get(user_col, "").strip()

    if not number or not created or not user:
        _log.debug("github_csv: skipping row — missing required field(s)")
        return None

    try:
        epoch = _parse_github_date(created)
    except ValueError:
        _log.debug("github_csv: skipping row %s — unparseable date %r", number, created)
        return None

    title_col = col.get("title")
    body_col = col.get("body")
    labels_col = col.get("labels")

    title = raw.get(title_col, "").strip() if title_col else None
    body = raw.get(body_col, "").strip() if body_col else None
    labels_raw = raw.get(labels_col, "").strip() if labels_col else ""

    module_keys = _build_module_keys(repo_module, labels_raw, label_modules)

    return {
        "id": f"github-issue-{number}",
        "occurred_at_epoch": epoch,
        "reporter_id": user,
        "title": title or None,
        "body": body or None,
        "module_keys": module_keys,
    }


def _parse_github_date(text: str) -> int:
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def _build_module_keys(
    repo_module: str | None,
    labels_raw: str,
    label_modules: Mapping[str, str],
) -> tuple[str, ...]:
    keys: set[str] = set()
    if repo_module:
        keys.add(repo_module)
    if labels_raw:
        for label in labels_raw.split(";"):
            label = label.strip()
            if label and label in label_modules:
                keys.add(label_modules[label])
    return tuple(sorted(keys))
