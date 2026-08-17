from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

_log = logging.getLogger(__name__)

# Confluence "Space Export" entities.xml date format: "2025-01-10 09:15:00.0"
# The trailing fractional-seconds component must be stripped before fromisoformat.
_CONFLUENCE_DATE_SUFFIX = ".0"


def confluence_xml_rows(
    path: Path,
    *,
    space_modules: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[dict[str, object], ...]:
    """Convert a Confluence space-export ``entities.xml`` into rows accepted by ``ticket_records``.

    Pass a directory path to have the function look for ``entities.xml`` inside it.
    ``space_modules`` maps Confluence space keys (e.g. ``"ENG"``) to module key tuples.
    """
    xml_path = _resolve_path(path)
    if xml_path is None:
        return ()

    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as exc:
        _log.debug("confluence_xml: failed to parse %s: %s", xml_path, exc)
        return ()

    root = tree.getroot()
    rows: list[dict[str, object]] = []
    for obj in root.findall("object"):
        kind = obj.get("class")
        if kind not in ("Page", "Comment"):
            continue
        row = _parse_object(obj, kind, space_modules or {})
        if row is not None:
            rows.append(row)

    rows.sort(key=lambda r: r["occurred_at_epoch"])
    return tuple(rows)


def _resolve_path(path: Path) -> Path | None:
    if path.is_dir():
        candidate = path / "entities.xml"
        return candidate if candidate.exists() else None
    return path if path.exists() else None


def _parse_object(
    obj: ET.Element,
    kind: str,
    space_modules: Mapping[str, tuple[str, ...]],
) -> dict[str, object] | None:
    obj_id = _text(obj, "id")
    creator = _prop(obj, "creatorName")
    date_str = _prop(obj, "creationDate")

    if not creator:
        _log.debug("confluence_xml: skipping %s id=%s — missing creatorName", kind, obj_id)
        return None
    if not date_str:
        _log.debug("confluence_xml: skipping %s id=%s — missing creationDate", kind, obj_id)
        return None

    try:
        epoch = _parse_confluence_date(date_str)
    except ValueError:
        _log.debug("confluence_xml: skipping %s id=%s — unparseable date %r", kind, obj_id, date_str)
        return None

    if kind == "Page":
        space = _prop(obj, "space") or ""
        title = _prop(obj, "title") or None
        return {
            "id": obj_id,
            "occurred_at_epoch": epoch,
            "reporter_id": creator,
            "title": title,
            "body": None,
            "module_keys": tuple(sorted(space_modules.get(space, ()))),
        }

    # Comment — title field is the comment text, stored as body; title is None.
    comment_title = _prop(obj, "title") or None
    return {
        "id": obj_id,
        "occurred_at_epoch": epoch,
        "reporter_id": creator,
        "title": None,
        "body": comment_title,
        "module_keys": (),
    }


def _parse_confluence_date(text: str) -> int:
    """Parse ``"2025-01-10 09:15:00.0"`` → Unix timestamp int."""
    clean = text.strip()
    if clean.endswith(_CONFLUENCE_DATE_SUFFIX):
        clean = clean[: -len(_CONFLUENCE_DATE_SUFFIX)]
    parsed = datetime.fromisoformat(clean)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def _text(obj: ET.Element, tag: str) -> str:
    """Return the text of the first direct child with the given tag name."""
    element = obj.find(tag)
    return (element.text or "").strip() if element is not None else ""


def _prop(obj: ET.Element, name: str) -> str:
    """Return the text content of ``<property name="...">`` child."""
    for prop in obj.findall("property"):
        if prop.get("name") == name:
            return (prop.text or "").strip()
    return ""
