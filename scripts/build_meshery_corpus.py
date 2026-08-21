"""Build the Meshery demo corpus (fixture + snapshot).

Default path (offline, no OAuth):
  1. Curated Meshery-shaped directory / events / git facts (or load from --fixture-out).
  2. Optional Meshery-shaped mock Slack JSON under data/exports/meshery/slack/.
  3. Optional public GitHub Issues CSV via GitHub API (rate-limit aware).
  4. Ingest → write data/snapshots/meshery-demo/.

Usage:
  uv run python scripts/build_meshery_corpus.py
  uv run python scripts/build_meshery_corpus.py --fetch-github
  uv run python scripts/build_meshery_corpus.py --slack-dir /path/to/unzipped/slack/export
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_ingest.manifest import write_snapshot
from xray_ingest.pipeline import ingest_exports

EMPTY_SHA = hashlib.sha256(b"").hexdigest()
DATASET_ID = "meshery-demo"
EPOCH = 1_735_689_600
COMM_EPOCH = 1_735_776_000

# Public Meshery maintainers / active contributors (handles as canonical ids).
PEOPLE: tuple[dict[str, Any], ...] = (
    {
        "id": "leecalcote",
        "display_name": "Lee Calcote",
        "title": "Project lead",
        "role_rank": 5,
        "team_key": "team:maintainers",
        "manager": None,
    },
    {
        "id": "aisuko",
        "display_name": "Aisuko",
        "title": "Server maintainer",
        "role_rank": 3,
        "team_key": "team:server",
        "manager": "leecalcote",
    },
    {
        "id": "muzairkhattak",
        "display_name": "Muhammad Uzair",
        "title": "UI maintainer",
        "role_rank": 3,
        "team_key": "team:ui",
        "manager": "leecalcote",
    },
    {
        "id": "alphaolomi",
        "display_name": "Alpha Olomi",
        "title": "mesheryctl maintainer",
        "role_rank": 3,
        "team_key": "team:cli",
        "manager": "leecalcote",
    },
    {
        "id": "sayantan15102",
        "display_name": "Sayantan Samanta",
        "title": "Provider engineer",
        "role_rank": 2,
        "team_key": "team:server",
        "manager": "aisuko",
    },
    {
        "id": "nithish",
        "display_name": "Nithish Karthik",
        "title": "UI engineer",
        "role_rank": 2,
        "team_key": "team:ui",
        "manager": "muzairkhattak",
    },
    {
        "id": "vishalvivekm",
        "display_name": "Vishal Vivek",
        "title": "Docs lead",
        "role_rank": 3,
        "team_key": "team:docs",
        "manager": "leecalcote",
    },
    {
        "id": "bridge-ops",
        "display_name": "Bridge Ops",
        "title": "Community bridge (IC)",
        "role_rank": 1,
        "team_key": "team:community",
        "manager": "leecalcote",
    },
    {
        "id": "nebula-reviewer",
        "display_name": "Nebula Reviewer",
        "title": "Reviewer",
        "role_rank": 2,
        "team_key": "team:server",
        "manager": "aisuko",
    },
)

MODULES: tuple[tuple[str, str], ...] = (
    ("server", "Meshery server"),
    ("ui", "Meshery UI"),
    ("mesheryctl", "mesheryctl CLI"),
    ("provider", "Remote provider"),
    ("docs", "Documentation"),
    ("nighthawk", "Nighthawk performance"),
)

MODULE_PREFIXES = {
    "server/": "server",
    "ui/": "ui",
    "mesheryctl/": "mesheryctl",
    "provider-ui/": "provider",
    "docs/": "docs",
    "install/": "docs",
    "scripts/": "server",
}


def main() -> int:
    args = _parse_args()
    fixture_out = Path(args.fixture_out)
    snapshot_out = Path(args.snapshot_out)
    export_root = Path(args.export_root)

    fixture_out.mkdir(parents=True, exist_ok=True)
    export_root.mkdir(parents=True, exist_ok=True)

    directory = _directory_records()
    events = _event_records()
    git_facts = _git_fact_records()

    if args.fetch_github:
        issues_csv = export_root / "github-issues.csv"
        _fetch_github_issues(issues_csv, limit=args.github_limit)
        print(f"wrote {issues_csv}")

    slack_dir = Path(args.slack_dir) if args.slack_dir else None
    if slack_dir is None:
        slack_dir = export_root / "slack"
        _write_mock_slack(slack_dir)
        print(f"wrote mock Slack export under {slack_dir}")
    else:
        print(f"using Slack export at {slack_dir}")

    _write_json(fixture_out / "directory.json", directory)
    _write_json(fixture_out / "events.json", events)
    _write_json(fixture_out / "git_facts.json", git_facts)
    manifest = _manifest(directory, events, git_facts)
    _write_json(fixture_out / "manifest.json", manifest)
    _write_json(fixture_out / "ground_truth.json", _ground_truth())
    _write_export_maps(export_root)

    contracts = SequenceContractSet.model_validate(
        {
            "contracts": manifest["sequence_contracts"],
            "limitations": manifest["limitations"],
        }
    )
    # directory.json only has people; modules live in git_facts
    directory_only = tuple(CanonicalRecord.model_validate(row) for row in directory)
    non_directory = tuple(
        CanonicalRecord.model_validate(row) for row in [*events, *git_facts]
    )
    bundle = ingest_exports(
        directory_records=directory_only,
        canonical_records=non_directory,
        contracts=contracts,
        dataset_id=DATASET_ID,
    )
    snap = write_snapshot(bundle, snapshot_out)
    print(f"fixture → {fixture_out}")
    print(f"snapshot → {snapshot_out} ({snap.snapshot_id})")
    print(f"nodes={len(bundle.nodes)} edges={len(bundle.edges)} evidence={len(bundle.evidence)}")
    return 0


def _parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-out",
        default=str(root / "data" / "fixtures" / "meshery-demo"),
    )
    parser.add_argument(
        "--snapshot-out",
        default=str(root / "data" / "snapshots" / "meshery-demo"),
    )
    parser.add_argument(
        "--export-root",
        default=str(root / "data" / "exports" / "meshery"),
    )
    parser.add_argument(
        "--slack-dir",
        default=None,
        help="Unzipped Slack workspace export (optional; mock written if omitted).",
    )
    parser.add_argument(
        "--fetch-github",
        action="store_true",
        help="Pull public meshery/meshery issues into github-issues.csv",
    )
    parser.add_argument("--github-limit", type=int, default=40)
    return parser.parse_args()


def _record(
    *,
    source: str,
    external_id: str,
    kind: str,
    subjects: list[str],
    metadata: dict[str, Any],
    occurred_at_epoch: int = EPOCH,
    author_external_id: str | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "external_id": external_id,
        "kind": kind,
        "occurred_at_epoch": occurred_at_epoch,
        "author_external_id": author_external_id,
        "parent_external_id": None,
        "subjects": subjects,
        "content_sha256": EMPTY_SHA,
        "content": None,
        "metadata": metadata,
    }


def _directory_records() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for person in PEOPLE:
        meta: dict[str, Any] = {
            "display_name": person["display_name"],
            "role_rank": person["role_rank"],
            "team_key": person["team_key"],
            "title": person["title"],
        }
        if person["manager"]:
            meta["manager_external_id"] = person["manager"]
        rows.append(
            _record(
                source="meshery-directory",
                external_id=person["id"],
                kind="directory_person",
                subjects=[f"person:{person['id']}"],
                metadata=meta,
            )
        )
    return rows


def _git_fact_records() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, label in MODULES:
        rows.append(
            _record(
                source="meshery-git",
                external_id=f"module-{key}",
                kind="module",
                subjects=[f"module:{key}"],
                metadata={"display_name": label, "module_external_id": key},
            )
        )

    ownership = (
        ("aisuko", "server", "github_codeowners", 95, 96),
        ("muzairkhattak", "ui", "github_codeowners", 95, 94),
        ("alphaolomi", "mesheryctl", "github_codeowners", 95, 93),
        ("sayantan15102", "provider", "jira_component_owner", 60, 78),
        ("vishalvivekm", "docs", "github_codeowners", 90, 90),
        ("aisuko", "nighthawk", "jira_component_owner", 60, 72),
        # Conflict: older ticket owner vs CODEOWNERS for server
        ("leecalcote", "server", "jira_component_owner", 60, 70),
    )
    for person, module, authority, rank, confidence in ownership:
        rows.append(
            _record(
                source="meshery-github" if "github" in authority else "meshery-tickets",
                external_id=f"owner-{person}-{module}-{authority}",
                kind="ownership_assertion",
                subjects=[f"person:{person}", f"module:{module}"],
                metadata={
                    "authority": authority,
                    "authority_rank": rank,
                    "confidence": confidence,
                    "valid_from_epoch": EPOCH - 86_400 * 90,
                    **(
                        {"valid_until_epoch": EPOCH - 86_400}
                        if person == "leecalcote" and module == "server"
                        else {}
                    ),
                },
            )
        )

    authorship = (
        ("aisuko", "server", 48),
        ("sayantan15102", "server", 18),
        ("muzairkhattak", "ui", 36),
        ("nithish", "ui", 14),
        ("alphaolomi", "mesheryctl", 28),
        ("sayantan15102", "provider", 22),
        ("vishalvivekm", "docs", 30),
        ("bridge-ops", "docs", 4),
        ("aisuko", "nighthawk", 12),
    )
    for person, module, count in authorship:
        rows.append(
            _record(
                source="meshery-git",
                external_id=f"authorship-{person}-{module}",
                kind="authorship_aggregate",
                subjects=[f"person:{person}", f"module:{module}"],
                author_external_id=person,
                metadata={
                    "attributed_count": count,
                    "module_external_id": module,
                    "total_attributed_count": count,
                },
            )
        )

    deps = (
        ("ui", "server", 18),
        ("mesheryctl", "server", 14),
        ("provider", "server", 11),
        ("docs", "ui", 6),
        ("nighthawk", "server", 9),
    )
    for source, target, weight in deps:
        rows.append(
            _record(
                source="meshery-git",
                external_id=f"dep-{source}-{target}",
                kind="dependency",
                subjects=[f"module:{source}", f"module:{target}"],
                metadata={
                    "dependency_kind": "import",
                    "source_module_external_id": source,
                    "target_module_external_id": target,
                    "weight": weight,
                },
            )
        )
    rows.append(
        _record(
            source="meshery-git",
            external_id="cochange-ui-provider",
            kind="cochange",
            subjects=["module:ui", "module:provider"],
            metadata={
                "cochange_count": 5,
                "relationship_class": "inferred_coupling",
                "source_module_external_id": "ui",
                "target_module_external_id": "provider",
            },
        )
    )
    return rows


def _event_records() -> list[dict[str, Any]]:
    """Communication aggregates + missing approval sequence for Gap lens."""
    # Ghost: bridge-ops (role_rank 1) is the communication hub.
    # Keep UI owners and server owners at distance >= 3 so ui→server is a faultline.
    pairs: list[tuple[str, str, int]] = [
        ("bridge-ops", "muzairkhattak", 22),
        ("bridge-ops", "alphaolomi", 20),
        ("bridge-ops", "nithish", 18),
        ("bridge-ops", "vishalvivekm", 16),
        ("bridge-ops", "nebula-reviewer", 15),
        ("bridge-ops", "leecalcote", 14),
        ("muzairkhattak", "nithish", 8),
        ("alphaolomi", "nithish", 4),
        # Server-side cluster (no short path to UI owners)
        ("aisuko", "sayantan15102", 7),
        ("leecalcote", "aisuko", 3),
        ("nebula-reviewer", "aisuko", 2),
        # Weak docs↔ui path still leaves provider→ui as a coordination risk when present
        ("vishalvivekm", "muzairkhattak", 2),
    ]
    rows: list[dict[str, Any]] = []
    for index, (sender, recipient, count) in enumerate(pairs):
        first = COMM_EPOCH + index * 40
        last = first + max(20, count)
        rows.append(
            _record(
                source="meshery-slack",
                external_id=f"comm-{sender}-{recipient}",
                kind="communication_aggregate",
                subjects=[f"person:{sender}", f"person:{recipient}"],
                author_external_id=sender,
                occurred_at_epoch=last,
                metadata={
                    "first_epoch": first,
                    "interaction_count": count,
                    "interaction_kind": "mention",
                    "last_epoch": last,
                    "recipient_external_id": recipient,
                    "sender_external_id": sender,
                },
            )
        )

    # Gap: directive + code change without required approval
    rows.append(
        _record(
            source="meshery-tickets",
            external_id="directive-designs-api",
            kind="artifact",
            subjects=["artifact:directive", "module:server"],
            author_external_id="leecalcote",
            occurred_at_epoch=EPOCH + 86_400,
            metadata={
                "artifact_kind": "directive",
                "canonical_key": "artifact:directive",
                "input_complete": True,
                "sequence_key": "meshery-change-approval",
                "sequence_ordinal": 0,
            },
        )
    )
    rows.append(
        _record(
            source="meshery-git",
            external_id="code-change-designs-api",
            kind="artifact",
            subjects=["artifact:code-change", "module:server"],
            author_external_id="aisuko",
            occurred_at_epoch=EPOCH + 86_400 * 3,
            metadata={
                "artifact_kind": "code_change",
                "canonical_key": "artifact:code-change",
                "input_complete": True,
                "sequence_key": "meshery-change-approval",
                "sequence_ordinal": 2,
            },
        )
    )
    return rows


def _manifest(
    directory: list[dict[str, Any]],
    events: list[dict[str, Any]],
    git_facts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "dataset_id": DATASET_ID,
        "fixture_version": 1,
        "schema_version": "1.0.0",
        "created_at_epoch": EPOCH,
        "evidence_classes": ["observed", "inferred", "demo_ground_truth"],
        "source_files": [
            {
                "path": "directory.json",
                "source_type": "directory",
                "source_uri": "fixture://meshery-demo/directory",
                "record_count": len(directory),
                "sha256": _payload_sha(directory),
                "input_status": "complete",
            },
            {
                "path": "events.json",
                "source_type": "event_export",
                "source_uri": "fixture://meshery-demo/events",
                "record_count": len(events),
                "sha256": _payload_sha(events),
                "input_status": "complete",
            },
            {
                "path": "git_facts.json",
                "source_type": "git",
                "source_uri": "fixture://meshery-demo/git-facts",
                "record_count": len(git_facts),
                "sha256": _payload_sha(git_facts),
                "input_status": "complete",
            },
        ],
        "ground_truth_file": "ground_truth.json",
        "ground_truth_descriptor": {
            "evidence_class": "demo_ground_truth",
            "sha256": EMPTY_SHA,
        },
        "sequence_contracts": [
            {
                "contract_id": "contract:meshery-approval-sequence:v1",
                "contract_kind": "contiguous_sequence",
                "sequence_key": "meshery-change-approval",
                "steps": [
                    {
                        "ordinal": 0,
                        "canonical_key": "artifact:directive",
                        "artifact_kind": "directive",
                        "required": True,
                    },
                    {
                        "ordinal": 1,
                        "canonical_key": "artifact:missing-approval",
                        "artifact_kind": "approval",
                        "required": True,
                    },
                    {
                        "ordinal": 2,
                        "canonical_key": "artifact:code-change",
                        "artifact_kind": "code_change",
                        "required": True,
                    },
                ],
                "source_uri": "fixture://meshery-demo/contracts/approval-sequence",
                "content_sha256": EMPTY_SHA,
                "limitations": [
                    "Slack mock fills communication edges until a real Meshery Slack export is provided.",
                ],
            }
        ],
        "acceptance_labels": {
            "ghost_broker_key": "person:bridge-ops",
            "owner_conflict_module_key": "module:server",
            "faultline_source_module_key": "module:ui",
            "faultline_target_module_key": "module:server",
        },
        "limitations": [
            "Dataset meshery-demo is snapshot analytics over public Meshery-shaped evidence, not a live HydraDB org connection.",
            "Slack edges are Meshery-shaped mock messages unless --slack-dir points at a real workspace export.",
            "GitHub Issues CSV is optional; ownership and dependency edges come from curated git facts when issues are not fetched.",
            "Absence does not establish deletion. The corpus is structurally incomplete at this point.",
        ],
    }


def _ground_truth() -> dict[str, Any]:
    return {
        "ghost_broker_key": "person:bridge-ops",
        "owner_conflict_module_key": "module:server",
        "missing_sequence_key": "meshery-change-approval",
        "notes": [
            "Bridge Ops is the load-bearing communicator despite IC formal rank.",
            "ui → server is a coordination faultline (owners rarely interact directly).",
            "Approval step is missing between directive and code change on server.",
        ],
    }


def _write_export_maps(export_root: Path) -> None:
    identity = {
        person["id"]: person["id"]
        for person in PEOPLE
    }
    # Also map GitHub-style emails / Slack handles
    for person in PEOPLE:
        identity[f"{person['id']}@users.noreply.github.com"] = person["id"]
        identity[f"@{person['id']}"] = person["id"]
    _write_json(export_root / "identity.json", identity)
    _write_json(export_root / "modules.json", MODULE_PREFIXES)
    _write_json(
        export_root / "directory.json",
        [
            {
                "external_id": p["id"],
                "display_name": p["display_name"],
                "title": p["title"],
                "role_rank": p["role_rank"],
                "team_key": p["team_key"],
                "manager_external_id": p["manager"],
            }
            for p in PEOPLE
        ],
    )


def _write_mock_slack(slack_dir: Path) -> None:
    """Minimal Slack export shape: channels.json + per-channel day files."""
    channel = "meshery-dev"
    channel_dir = slack_dir / channel
    channel_dir.mkdir(parents=True, exist_ok=True)
    channels = [
        {
            "id": "C0MESHERY",
            "name": channel,
            "created": EPOCH,
            "creator": "U0LEE",
            "is_archived": False,
            "is_general": False,
            "members": [f"U0{p['id'].upper()[:6]}" for p in PEOPLE],
            "topic": {"value": "Meshery core development"},
            "purpose": {"value": "Mock export for X-Ray demo until a real Slack zip is provided"},
        }
    ]
    users = [
        {
            "id": f"U0{p['id'].upper()[:6]}",
            "name": p["id"],
            "real_name": p["display_name"],
            "profile": {"display_name": p["display_name"], "real_name": p["display_name"]},
        }
        for p in PEOPLE
    ]
    _write_json(slack_dir / "channels.json", channels)
    _write_json(slack_dir / "users.json", users)

    messages: list[dict[str, Any]] = []
    ts = float(COMM_EPOCH)
    scripts = [
        ("bridge-ops", "Need eyes on the designs API change before UI ships."),
        ("aisuko", "Server PR is up — waiting on review."),
        ("muzairkhattak", "UI blocked on provider schema."),
        ("bridge-ops", "@aisuko @muzairkhattak can we sync on the server contract?"),
        ("alphaolomi", "mesheryctl needs the new flag mirrored in server."),
        ("bridge-ops", "I'll thread the ownership question so docs stay current."),
        ("nithish", "Component library bump is ready for review."),
        ("bridge-ops", "@nithish pairing with @muzairkhattak on the regression."),
        ("vishalvivekm", "Docs for the new provider flow — please confirm owners."),
        ("bridge-ops", "Tracking: server CODEOWNERS vs older ticket assignee conflict."),
        ("sayantan15102", "Provider remote path ready for mesheryctl."),
        ("nebula-reviewer", "LGTM on the server side with nits."),
        ("bridge-ops", "Still no recorded approval artifact for the designs API directive."),
        ("leecalcote", "Please keep the design review trail in the ticket."),
    ]
    user_by_handle = {p["id"]: f"U0{p['id'].upper()[:6]}" for p in PEOPLE}
    for handle, text in scripts:
        messages.append(
            {
                "type": "message",
                "user": user_by_handle[handle],
                "text": text,
                "ts": f"{ts:.6f}",
            }
        )
        ts += 120.0
    _write_json(channel_dir / "2025-01-15.json", messages)


def _fetch_github_issues(out_path: Path, *, limit: int) -> None:
    """Download public issues for meshery/meshery into the GitHub CSV adapter shape."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "xray-meshery-corpus-builder",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    issues: list[dict[str, Any]] = []
    page = 1
    while len(issues) < limit:
        url = (
            "https://api.github.com/repos/meshery/meshery/issues"
            f"?state=all&per_page=50&page={page}"
        )
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                batch = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            print(f"GitHub fetch stopped: HTTP {exc.code}")
            break
        if not isinstance(batch, list) or not batch:
            break
        for item in batch:
            if "pull_request" in item:
                continue
            issues.append(item)
            if len(issues) >= limit:
                break
        page += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "number",
        "title",
        "state",
        "user",
        "assignees",
        "labels",
        "created_at",
        "updated_at",
        "closed_at",
        "body",
        "html_url",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in issues:
            writer.writerow(
                {
                    "id": item.get("id"),
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "state": item.get("state"),
                    "user": (item.get("user") or {}).get("login"),
                    "assignees": ",".join(
                        a.get("login", "") for a in (item.get("assignees") or [])
                    ),
                    "labels": ",".join(
                        label.get("name", "") for label in (item.get("labels") or [])
                    ),
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                    "closed_at": item.get("closed_at"),
                    "body": (item.get("body") or "")[:2000],
                    "html_url": item.get("html_url"),
                }
            )


def _payload_sha(rows: list[dict[str, Any]]) -> str:
    blob = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
