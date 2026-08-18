"""Salesforce HERB adapter — the official Hack Hydra Track 01 corpus.

HERB (arXiv 2506.23139) ships one JSON file per product plus ``metadata/employee.json``
and ``metadata/salesforce_team.json``. Everything X-Ray needs is *explicit* in the data,
so this adapter follows the same rule as every other adapter: it reads ids, it never
guesses them from prose.

What becomes what:

* ``metadata/employee.json`` + ``salesforce_team.json`` → ``directory_person`` records
  with ``role_rank`` taken from the stated role (VP/CPO = 6 … engineer/QA = 1) and
  ``team_key`` from the engineering lead the person reports to.
* one ``module`` record per product file.
* ``slack[]`` → Slack rows. The author is ``Message.User.userId``; recipients are the
  explicit ``@eid_…`` mentions in the text. HERB Slack has no thread metadata, so no
  ``thread_parent_id`` is emitted — the corpus is structurally flat here and the Gaps
  lens will say so rather than invent parents.
* ``prs[]`` → one git row per PR (author = ``user.login``, module = the product) and one
  Slack-style *reply* row per review (reviewer → PR author). A review is the one place
  HERB records an explicit reply relationship, so it is the backbone of the human graph.
* ``documents[]`` → ticket rows (author, date, product) for ownership evidence.
* ``meeting_transcripts[]`` are **not** ingested: attendance is not communication, and
  X-Ray does not derive edges from co-presence.

PR ``user.login`` values are a separate id space (``EMP_…``) from employee ids
(``eid_…``); HERB provides no mapping, so those authors resolve to visible
``unresolved-…`` handles unless the caller supplies one in ``identity_map``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_EID = re.compile(r"eid_[0-9a-f]{8}")

# Spec §3.1 role_rank scale: 0=unknown, 1=IC, 2=senior, 3=lead, 4=manager, 5=director, 6=VP+.
ROLE_RANKS: Mapping[str, int] = {
    "chief product officer": 6,
    "vp of engineering": 6,
    "vp": 6,
    "director": 5,
    "engineering lead": 3,
    "technical architect": 3,
    "product manager": 3,
    "marketing manager": 3,
    "ux researcher": 2,
    "marketing research analyst": 2,
    "software engineer": 1,
    "qa specialist": 1,
}


def herb_role_rank(role: str) -> int:
    key = role.strip().lower()
    if key in ROLE_RANKS:
        return ROLE_RANKS[key]
    for needle, rank in ROLE_RANKS.items():
        if needle in key:
            return rank
    return 0


# ── directory ────────────────────────────────────────────────────────────────


def herb_directory_records(
    employee_json: Path,
    team_json: Path,
    product_names: Iterable[str],
    *,
    epoch: int = 1735689600,
    source: str = "herb-directory",
) -> tuple[dict[str, Any], ...]:
    """Build canonical ``directory_person`` + ``module`` records from HERB metadata."""
    employees = json.loads(employee_json.read_text(encoding="utf-8"))
    if not isinstance(employees, dict):
        raise ValueError("employee.json must map employee_id -> profile")
    team_of = _team_index(json.loads(team_json.read_text(encoding="utf-8")))

    records: list[dict[str, Any]] = []
    for eid, profile in sorted(employees.items()):
        if not isinstance(profile, dict):
            continue
        name = str(profile.get("name") or eid)
        role = str(profile.get("role") or "")
        team_key = team_of.get(eid, f"team:{profile.get('org', 'unknown')}")
        records.append(
            _canonical(
                external_id=eid,
                kind="directory_person",
                epoch=epoch,
                source=source,
                subjects=[f"person:{eid}"],
                metadata={
                    "display_name": name,
                    "role_rank": herb_role_rank(role),
                    "role": role,
                    "location": profile.get("location"),
                    "team_key": team_key,
                    "source_identity_count": 1,
                },
            )
        )
    for product in sorted(set(product_names)):
        key = _module_key(product)
        records.append(
            _canonical(
                external_id=key,
                kind="module",
                epoch=epoch,
                source=source,
                subjects=[f"module:{key}"],
                metadata={"canonical_key": f"module:{key}", "criticality": 1.0, "product": product},
            )
        )
    return tuple(records)


def _team_index(team_tree: Any) -> dict[str, str]:
    """Map every employee id to ``team:<lead-eid>`` — the engineering lead they sit under.

    Leads and above map to their own team; product/marketing/UX roles hang off the VP.
    """
    index: dict[str, str] = {}
    vps = team_tree if isinstance(team_tree, list) else [team_tree]
    for vp in vps:
        if not isinstance(vp, dict):
            continue
        vp_id = str(vp.get("employee_id", "vp"))
        index[vp_id] = f"team:{vp_id}"
        for lead in vp.get("engineering_leads", []) or []:
            if not isinstance(lead, dict):
                continue
            lead_id = str(lead.get("employee_id", "lead"))
            team = f"team:{lead_id}"
            index[lead_id] = team
            for group in ("engineers", "qa_specialists"):
                for member in lead.get(group, []) or []:
                    if isinstance(member, dict) and "employee_id" in member:
                        index[str(member["employee_id"])] = team
        for group, members in vp.items():
            if group in {"engineering_leads", "employee_id", "name", "role", "location", "org"}:
                continue
            if isinstance(members, list):
                for member in members:
                    if isinstance(member, dict) and "employee_id" in member:
                        index.setdefault(str(member["employee_id"]), f"team:{vp_id}")
    return index


# ── artifacts ────────────────────────────────────────────────────────────────


def herb_slack_rows(product_json: Path) -> tuple[dict[str, object], ...]:
    """Slack rows: explicit author + explicit ``@eid`` mentions, module = product."""
    product, payload = _load_product(product_json)
    module = _module_key(product)
    rows: list[dict[str, object]] = []
    for item in payload.get("slack", []) or []:
        message = _get(item, "Message", "User")
        if not isinstance(message, dict):
            continue
        author = message.get("userId")
        text = message.get("text")
        stamp = message.get("timestamp")
        if not isinstance(author, str) or not isinstance(stamp, str):
            continue
        # HERB's channel-admin bot is a relay, not a person.
        if not author.startswith("eid_"):
            continue
        epoch = _epoch(stamp)
        if epoch is None:
            continue
        mentions = tuple(sorted({m for m in _EID.findall(text or "") if m != author}))
        channel = _get(item, "Channel", "name") or "slack"
        rows.append(
            {
                "id": f"herb:{product}:slack:{item.get('id') or message.get('utterranceID')}",
                "occurred_at_epoch": epoch,
                "author_id": author,
                "thread_parent_id": None,
                "parent_author_id": None,
                "mentions": mentions,
                "module_keys": (module,),
                "text": text if isinstance(text, str) else None,
                "channel": str(channel),
            }
        )
    rows.sort(key=lambda r: (r["occurred_at_epoch"], str(r["id"])))
    return tuple(rows)


def herb_pr_rows(
    product_json: Path,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    """Return ``(git_rows, review_rows)`` for a product's pull requests.

    ``git_rows`` feed the work graph (author → module). ``review_rows`` are Slack-style
    replies (reviewer → PR author) and feed the human graph.
    """
    product, payload = _load_product(product_json)
    module = _module_key(product)
    git_rows: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []
    for pr in payload.get("prs", []) or []:
        if not isinstance(pr, dict):
            continue
        pr_id = str(pr.get("id") or f"pr-{pr.get('number')}")
        author = _get(pr, "user", "login")
        epoch = _epoch(str(pr.get("created_at", "")))
        if not isinstance(author, str) or epoch is None:
            continue
        artifact_id = f"herb:{product}:pr:{pr_id}"
        git_rows.append(
            {
                "sha": artifact_id,
                "occurred_at_epoch": epoch,
                "author_id": author,
                "message": str(pr.get("title") or ""),
                "module_keys": (module,),
                "dependency_keys": (),
            }
        )
        for index, review in enumerate(pr.get("reviews", []) or []):
            if not isinstance(review, dict):
                continue
            reviewer = _get(review, "user", "login")
            r_epoch = _epoch(str(review.get("submitted_at", ""))) or epoch
            if not isinstance(reviewer, str):
                continue
            review_rows.append(
                {
                    "id": f"{artifact_id}:review:{index}",
                    "occurred_at_epoch": r_epoch,
                    "author_id": reviewer,
                    "thread_parent_id": f"artifact:git:{artifact_id}",
                    "parent_author_id": author,
                    "mentions": (),
                    "module_keys": (module,),
                    "text": review.get("comment")
                    if isinstance(review.get("comment"), str)
                    else None,
                    "channel": f"pr:{product}",
                }
            )
    git_rows.sort(key=lambda r: (r["occurred_at_epoch"], str(r["sha"])))
    review_rows.sort(key=lambda r: (r["occurred_at_epoch"], str(r["id"])))
    return tuple(git_rows), tuple(review_rows)


def herb_document_rows(product_json: Path) -> tuple[dict[str, object], ...]:
    """Documents as ticket rows: explicit author + date + product module."""
    product, payload = _load_product(product_json)
    module = _module_key(product)
    rows: list[dict[str, object]] = []
    for doc in payload.get("documents", []) or []:
        if not isinstance(doc, dict):
            continue
        author = doc.get("author")
        epoch = _epoch(str(doc.get("date", "")))
        if not isinstance(author, str) or epoch is None:
            continue
        rows.append(
            {
                "id": f"herb:{product}:doc:{doc.get('id')}",
                "occurred_at_epoch": epoch,
                "reporter_id": author,
                "title": str(doc.get("type") or "document"),
                "body": None,
                "module_keys": (module,),
            }
        )
    rows.sort(key=lambda r: (r["occurred_at_epoch"], str(r["id"])))
    return tuple(rows)


def herb_product_name(product_json: Path) -> str:
    return product_json.stem


# ── helpers ──────────────────────────────────────────────────────────────────


def _load_product(path: Path) -> tuple[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return path.stem, payload


def _module_key(product: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", product.lower()).strip("-")


def _get(obj: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _epoch(stamp: str) -> int | None:
    stamp = stamp.strip()
    if not stamp:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(stamp, fmt).replace(tzinfo=UTC).timestamp())
        except ValueError:
            continue
    return None


def _canonical(
    *,
    external_id: str,
    kind: str,
    epoch: int,
    source: str,
    subjects: list[str],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "author_external_id": None,
        "content": None,
        "content_sha256": EMPTY_SHA256,
        "external_id": external_id,
        "kind": kind,
        "metadata": metadata,
        "occurred_at_epoch": epoch,
        "parent_external_id": None,
        "source": source,
        "subjects": subjects,
    }
