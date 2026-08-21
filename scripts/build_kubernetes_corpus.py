"""Build the Kubernetes full-org demo corpus (fixture + snapshot).

Offline by default (no OAuth). Pulls public governance + org metadata:

  1. ``sigs.yaml`` from kubernetes/community (SIGs, WGs, chairs, tech leads).
  2. Public repos from ``kubernetes`` and ``kubernetes-sigs`` GitHub orgs.
  3. Curated cross-SIG dependency + communication graph shaped for Ghost /
     Faultline / Gap lenses (plus optional mock Slack).
  4. Optional ``--fetch-github`` Issues CSV for top repos.
  5. Ingest → ``data/snapshots/kubernetes-demo/``.

Usage:
  uv run python scripts/build_kubernetes_corpus.py
  uv run python scripts/build_kubernetes_corpus.py --fetch-github
  uv run python scripts/build_kubernetes_corpus.py --slack-dir /path/to/slack/export
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml
from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_ingest.manifest import write_snapshot
from xray_ingest.pipeline import ingest_exports

EMPTY_SHA = hashlib.sha256(b"").hexdigest()
DATASET_ID = "kubernetes-demo"
EPOCH = 1_735_689_600
COMM_EPOCH = 1_735_776_000
SIGS_YAML_URL = (
    "https://raw.githubusercontent.com/kubernetes/community/master/sigs.yaml"
)
ORG_REPOS = ("kubernetes", "kubernetes-sigs")
UA = "xray-kubernetes-corpus-builder"

# Cross-SIG technical dependencies that create coordination risk when owners
# do not share a short communication path (Faultline lens).
CROSS_SIG_DEPS: tuple[tuple[str, str, int], ...] = (
    ("network", "api-machinery", 22),
    ("scheduling", "node", 20),
    ("scheduling", "apps", 16),
    ("storage", "api-machinery", 18),
    ("auth", "api-machinery", 17),
    ("cli", "apps", 14),
    ("instrumentation", "architecture", 12),
    ("cluster-lifecycle", "node", 15),
    ("autoscaling", "scheduling", 13),
    ("windows", "node", 11),
    ("cloud-provider", "api-machinery", 14),
    ("scalability", "instrumentation", 10),
    ("testing", "architecture", 9),
    ("docs", "cli", 8),
    ("contributor-experience", "docs", 7),
    ("k8s-infra", "cluster-lifecycle", 11),
    ("security", "auth", 16),
    ("multicluster", "network", 10),
    ("ui", "cli", 8),
    ("etcd", "api-machinery", 15),
)


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-out",
        default=str(root / "data" / "fixtures" / "kubernetes-demo"),
    )
    parser.add_argument(
        "--snapshot-out",
        default=str(root / "data" / "snapshots" / "kubernetes-demo"),
    )
    parser.add_argument(
        "--export-out",
        default=str(root / "data" / "exports" / "kubernetes"),
    )
    parser.add_argument("--slack-dir", default="")
    parser.add_argument(
        "--fetch-github",
        action="store_true",
        help="Pull public Issues CSV for top kubernetes org repos",
    )
    parser.add_argument("--github-issue-limit", type=int, default=200)
    args = parser.parse_args(argv)

    fixture_out = Path(args.fixture_out)
    snapshot_out = Path(args.snapshot_out)
    export_out = Path(args.export_out)
    fixture_out.mkdir(parents=True, exist_ok=True)
    export_out.mkdir(parents=True, exist_ok=True)

    print("Fetching sigs.yaml …")
    governance = _load_sigs_yaml()
    print("Listing kubernetes + kubernetes-sigs repos …")
    repos = _list_org_repos()
    people, modules, sig_meta = _people_and_modules(governance, repos)
    print(
        f"Built {len(people)} people, {len(modules)} modules "
        f"from {len(sig_meta)} SIGs/WGs and {len(repos)} repos"
    )

    directory = _directory_records(people)
    events = _event_records(people, sig_meta)
    git_facts = _git_fact_records(people, modules, sig_meta, repos)
    manifest = _manifest(directory, events, git_facts, len(repos))
    ground_truth = _ground_truth(sig_meta)

    for name, payload in (
        ("directory.json", directory),
        ("events.json", events),
        ("git_facts.json", git_facts),
        ("manifest.json", manifest),
        ("ground_truth.json", ground_truth),
    ):
        _write_json(fixture_out / name, payload)

    _write_export_maps(export_out, people, modules)

    slack_dir = Path(args.slack_dir) if args.slack_dir else export_out / "slack"
    if not args.slack_dir:
        _write_mock_slack(slack_dir, people, sig_meta)
        print(f"Wrote mock Slack export → {slack_dir}")

    if args.fetch_github:
        csv_path = export_out / "github-issues.csv"
        _fetch_github_issues(csv_path, limit=args.github_issue_limit, repos=repos)
        print(f"Wrote GitHub issues CSV → {csv_path} ({args.github_issue_limit} cap)")

    records = [
        CanonicalRecord.model_validate(row)
        for row in (*directory, *events, *git_facts)
    ]
    directory_records = tuple(r for r in records if r.kind == "directory_person")
    canonical_records = tuple(r for r in records if r.kind != "directory_person")
    contracts = SequenceContractSet.model_validate(
        {
            "contracts": manifest["sequence_contracts"],
            "limitations": manifest["limitations"],
        }
    )
    bundle = ingest_exports(
        directory_records=directory_records,
        canonical_records=canonical_records,
        contracts=contracts,
        dataset_id=DATASET_ID,
    )
    write_snapshot(bundle, snapshot_out)
    print(
        f"Snapshot {DATASET_ID}: nodes={len(bundle.nodes)} "
        f"edges={len(bundle.edges)} evidence={len(bundle.evidence)} → {snapshot_out}"
    )
    return 0


def _load_sigs_yaml() -> dict[str, Any]:
    req = urllib.request.Request(SIGS_YAML_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as response:
        return yaml.safe_load(response.read().decode("utf-8"))


def _list_org_repos() -> list[dict[str, Any]]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    out: list[dict[str, Any]] = []
    for org in ORG_REPOS:
        page = 1
        while page <= 20:
            url = (
                f"https://api.github.com/orgs/{org}/repos"
                f"?per_page=100&page={page}&type=public"
            )
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=45) as response:
                    batch = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                print(f"Repo list {org} page {page} stopped: HTTP {exc.code}")
                break
            if not isinstance(batch, list) or not batch:
                break
            for item in batch:
                if item.get("archived"):
                    continue
                out.append(
                    {
                        "org": org,
                        "name": item["name"],
                        "full_name": item["full_name"],
                        "description": item.get("description") or "",
                        "open_issues": int(item.get("open_issues_count") or 0),
                        "stars": int(item.get("stargazers_count") or 0),
                        "default_branch": item.get("default_branch") or "main",
                        "topics": list(item.get("topics") or []),
                    }
                )
            if len(batch) < 100:
                break
            page += 1
    out.sort(key=lambda r: (-r["open_issues"], -r["stars"], r["full_name"]))
    return out


def _people_and_modules(
    governance: dict[str, Any], repos: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    sig_meta: list[dict[str, Any]] = []
    people_by_id: dict[str, dict[str, Any]] = {}
    modules: list[dict[str, Any]] = []
    module_keys: set[str] = set()

    def add_module(key: str, label: str, kind: str) -> None:
        if key in module_keys:
            return
        module_keys.add(key)
        modules.append({"key": key, "label": label, "kind": kind})

    def add_person(
        github: str,
        *,
        name: str,
        title: str,
        role_rank: int,
        team_key: str,
        manager: str | None,
    ) -> None:
        handle = _slug(github)
        if not handle or handle in people_by_id:
            # Keep higher formal rank if we see the same person again.
            if handle in people_by_id and role_rank > people_by_id[handle]["role_rank"]:
                people_by_id[handle]["role_rank"] = role_rank
                people_by_id[handle]["title"] = title
            return
        people_by_id[handle] = {
            "id": handle,
            "display_name": name or handle,
            "title": title,
            "role_rank": role_rank,
            "team_key": team_key,
            "manager": manager,
        }

    for group_kind, bucket in (
        ("sig", governance.get("sigs") or []),
        ("wg", governance.get("workinggroups") or []),
        ("committee", governance.get("committees") or []),
    ):
        for entry in bucket:
            dir_name = str(entry.get("dir") or entry.get("name") or "").strip()
            if not dir_name:
                continue
            slug = dir_name.replace("sig-", "").replace("wg-", "").replace("committee-", "")
            module_key = slug
            label = str(entry.get("name") or dir_name)
            add_module(module_key, label, group_kind)
            leadership = entry.get("leadership") or {}
            chairs = list(leadership.get("chairs") or [])
            tech_leads = list(leadership.get("tech_leads") or [])
            chair_ids: list[str] = []
            for chair in chairs:
                gh = str(chair.get("github") or "").strip()
                if not gh:
                    continue
                add_person(
                    gh,
                    name=str(chair.get("name") or gh),
                    title=f"{label} chair",
                    role_rank=5 if group_kind == "committee" else 4,
                    team_key=f"team:{module_key}",
                    manager=None,
                )
                chair_ids.append(_slug(gh))
            lead_manager = chair_ids[0] if chair_ids else None
            for lead in tech_leads:
                gh = str(lead.get("github") or "").strip()
                if not gh:
                    continue
                add_person(
                    gh,
                    name=str(lead.get("name") or gh),
                    title=f"{label} tech lead",
                    role_rank=3,
                    team_key=f"team:{module_key}",
                    manager=lead_manager,
                )
            contact = entry.get("contact") or {}
            slack = ""
            slack_field = contact.get("slack")
            if isinstance(slack_field, str):
                slack = slack_field
            elif isinstance(slack_field, list) and slack_field:
                slack = str(slack_field[0])
            sig_meta.append(
                {
                    "kind": group_kind,
                    "dir": dir_name,
                    "slug": module_key,
                    "label": label,
                    "chairs": chair_ids,
                    "tech_leads": [_slug(str(t.get("github") or "")) for t in tech_leads],
                    "slack": slack or f"sig-{module_key}",
                }
            )

    # Synthetic ghost bridge — high communication, low formal rank.
    add_person(
        "k8s-bridge-ops",
        name="K8s Bridge Ops",
        title="Cross-SIG coordinator (IC)",
        role_rank=1,
        team_key="team:contributor-experience",
        manager=people_by_id.get("mrbobbytables", {}).get("id")
        or (sig_meta[0]["chairs"][0] if sig_meta and sig_meta[0]["chairs"] else None),
    )
    add_person(
        "kep-shepherd",
        name="KEP Shepherd",
        title="Enhancements shepherd",
        role_rank=2,
        team_key="team:architecture",
        manager=None,
    )

    # Repo modules across both orgs.
    sig_slugs = {s["slug"] for s in sig_meta}
    for repo in repos:
        key = f"repo-{repo['org']}-{repo['name']}"
        add_module(key, repo["full_name"], "repo")
        owner_sig = _guess_sig_for_repo(repo, sig_slugs)
        repo["owner_sig"] = owner_sig

    people = sorted(people_by_id.values(), key=lambda p: p["id"])
    # Fill missing managers with first chair of their team when possible.
    chairs_by_team = {
        f"team:{s['slug']}": (s["chairs"][0] if s["chairs"] else None) for s in sig_meta
    }
    for person in people:
        if person["manager"] is None and person["id"] not in {
            c for s in sig_meta for c in s["chairs"]
        }:
            person["manager"] = chairs_by_team.get(person["team_key"])
    return people, modules, sig_meta


def _guess_sig_for_repo(repo: dict[str, Any], sig_slugs: set[str]) -> str | None:
    blob = " ".join(
        [
            repo["name"],
            repo.get("description") or "",
            " ".join(repo.get("topics") or []),
        ]
    ).lower()
    for topic in repo.get("topics") or []:
        m = re.search(r"k8s-sig-([a-z0-9-]+)", topic.lower())
        if m and m.group(1) in sig_slugs:
            return m.group(1)
    for slug in sorted(sig_slugs, key=len, reverse=True):
        if slug in blob.replace("_", "-"):
            return slug
    keywords = {
        "network": "network",
        "cni": "network",
        "schedule": "scheduling",
        "storage": "storage",
        "csi": "storage",
        "auth": "auth",
        "kubectl": "cli",
        "cli": "cli",
        "docs": "docs",
        "website": "docs",
        "test": "testing",
        "node": "node",
        "cloud": "cloud-provider",
        "window": "windows",
        "instrument": "instrumentation",
        "metric": "instrumentation",
        "cluster": "cluster-lifecycle",
        "release": "release",
        "security": "security",
        "api": "api-machinery",
        "client": "api-machinery",
        "app": "apps",
        "autoscal": "autoscaling",
        "multi": "multicluster",
        "contrib": "contributor-experience",
        "infra": "k8s-infra",
        "etcd": "etcd",
        "ui": "ui",
    }
    for needle, slug in keywords.items():
        if needle in blob and slug in sig_slugs:
            return slug
    return None


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


def _directory_records(people: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for person in people:
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
                source="kubernetes-sigs-yaml",
                external_id=person["id"],
                kind="directory_person",
                subjects=[f"person:{person['id']}"],
                metadata=meta,
            )
        )
    return rows


def _event_records(
    people: list[dict[str, Any]], sig_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    people_ids = {p["id"] for p in people}
    bridge = "k8s-bridge-ops" if "k8s-bridge-ops" in people_ids else next(iter(people_ids))
    isolated_from_bridge = {dst for _src, dst, _weight in CROSS_SIG_DEPS}
    seen_pairs: set[tuple[str, str]] = set()
    index = 0

    def add_comm(sender: str, recipient: str, count: int) -> None:
        nonlocal index
        if sender not in people_ids or recipient not in people_ids or sender == recipient:
            return
        key = tuple(sorted((sender, recipient)))
        if key in seen_pairs:
            return
        seen_pairs.add(key)
        first = COMM_EPOCH + index * 40
        last = first + max(20, count)
        index += 1
        rows.append(
            _record(
                source="kubernetes-slack-mock",
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

    for sig in sig_meta:
        members = [m for m in (*sig["chairs"], *sig["tech_leads"]) if m in people_ids]
        for i, left in enumerate(members):
            for right in members[i + 1 :]:
                add_comm(left, right, 6)
        # Bridge hubs most SIGs for Ghost; keep CROSS_SIG target SIGs off the
        # bridge so dependent owners stay at distance >= 3 (Faultline).
        if sig["slug"] in isolated_from_bridge:
            continue
        for chair in sig["chairs"]:
            if chair != bridge:
                add_comm(bridge, chair, 12)

    # Soft bridge contact only on the source side of each faultline dep.
    for src, _dst, _weight in CROSS_SIG_DEPS:
        src_sig = next((s for s in sig_meta if s["slug"] == src), None)
        if src_sig and src_sig["chairs"]:
            add_comm(bridge, src_sig["chairs"][0], 5)

    rows.append(
        _record(
            source="kubernetes-kep",
            external_id="directive-cross-sig-api",
            kind="artifact",
            subjects=["artifact:directive", "module:api-machinery"],
            author_external_id=bridge,
            occurred_at_epoch=EPOCH + 86_400,
            metadata={
                "artifact_kind": "directive",
                "canonical_key": "artifact:directive",
                "display_name": "KEP: cross-SIG API change",
                "input_complete": True,
                "sequence_key": "k8s-kep-approval",
                "sequence_ordinal": 0,
            },
        )
    )
    rows.append(
        _record(
            source="kubernetes-kep",
            external_id="code-change-cross-sig-api",
            kind="artifact",
            subjects=["artifact:code-change", "module:network"],
            author_external_id=bridge,
            occurred_at_epoch=EPOCH + 86_400 * 5,
            metadata={
                "artifact_kind": "code_change",
                "canonical_key": "artifact:code-change",
                "display_name": "Merge API change without recorded approval",
                "input_complete": True,
                "sequence_key": "k8s-kep-approval",
                "sequence_ordinal": 2,
            },
        )
    )
    return rows


def _git_fact_records(
    people: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    sig_meta: list[dict[str, Any]],
    repos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    module_keys = {m["key"] for m in modules}
    people_ids = {p["id"] for p in people}

    for module in modules:
        rows.append(
            _record(
                source="kubernetes-org",
                external_id=f"module-{module['key']}",
                kind="module",
                subjects=[f"module:{module['key']}"],
                metadata={
                    "display_name": module["label"],
                    "module_external_id": module["key"],
                    "module_kind": module["kind"],
                },
            )
        )

    for sig in sig_meta:
        if sig["slug"] not in module_keys:
            continue
        owners = list(
            dict.fromkeys(
                o for o in (*sig["chairs"], *sig["tech_leads"]) if o in people_ids
            )
        )[:4]
        attributed = [40 - idx * 5 for idx in range(len(owners))]
        total_attributed = sum(attributed) or 1
        for idx, owner in enumerate(owners):
            conf = 96 - idx * 3
            rows.append(
                _record(
                    source="kubernetes-owners",
                    external_id=f"owner-{owner}-{sig['slug']}-{idx}",
                    kind="ownership_assertion",
                    subjects=[f"person:{owner}", f"module:{sig['slug']}"],
                    metadata={
                        "authority": "sigs_yaml_leadership",
                        "authority_rank": 95 - idx,
                        "confidence": conf,
                        "valid_from_epoch": EPOCH - 86_400 * 90,
                    },
                )
            )
            rows.append(
                _record(
                    source="kubernetes-git",
                    external_id=f"auth-{owner}-{sig['slug']}-{idx}",
                    kind="authorship_aggregate",
                    subjects=[f"person:{owner}", f"module:{sig['slug']}"],
                    author_external_id=owner,
                    metadata={
                        "attributed_count": attributed[idx],
                        "module_external_id": sig["slug"],
                        "total_attributed_count": total_attributed,
                    },
                )
            )

    for repo in repos:
        key = f"repo-{repo['org']}-{repo['name']}"
        if key not in module_keys:
            continue
        owner_sig = repo.get("owner_sig")
        sig = next((s for s in sig_meta if s["slug"] == owner_sig), None)
        owner = None
        if sig:
            for candidate in (*sig["chairs"], *sig["tech_leads"]):
                if candidate in people_ids:
                    owner = candidate
                    break
        if owner is None:
            continue
        rows.append(
            _record(
                source="kubernetes-repo-map",
                external_id=f"owner-{owner}-{key}",
                kind="ownership_assertion",
                subjects=[f"person:{owner}", f"module:{key}"],
                metadata={
                    "authority": "sig_topic_heuristic",
                    "authority_rank": 70,
                    "confidence": 80,
                    "valid_from_epoch": EPOCH - 86_400 * 30,
                },
            )
        )
        if owner_sig and owner_sig in module_keys:
            rows.append(
                _record(
                    source="kubernetes-org",
                    external_id=f"dep-{key}-{owner_sig}",
                    kind="dependency",
                    subjects=[f"module:{key}", f"module:{owner_sig}"],
                    metadata={
                        "dependency_kind": "explicit_reference",
                        "source_module_external_id": key,
                        "target_module_external_id": owner_sig,
                        "weight": 6,
                    },
                )
            )

    for src, dst, weight in CROSS_SIG_DEPS:
        if src in module_keys and dst in module_keys:
            rows.append(
                _record(
                    source="kubernetes-architecture",
                    external_id=f"dep-{src}-{dst}",
                    kind="dependency",
                    subjects=[f"module:{src}", f"module:{dst}"],
                    metadata={
                        "dependency_kind": "import",
                        "source_module_external_id": src,
                        "target_module_external_id": dst,
                        "weight": weight,
                    },
                )
            )
    return rows


def _manifest(
    directory: list[dict[str, Any]],
    events: list[dict[str, Any]],
    git_facts: list[dict[str, Any]],
    repo_count: int,
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
                "source_uri": "fixture://kubernetes-demo/directory",
                "record_count": len(directory),
                "sha256": _payload_sha(directory),
                "input_status": "complete",
            },
            {
                "path": "events.json",
                "source_type": "event_export",
                "source_uri": "fixture://kubernetes-demo/events",
                "record_count": len(events),
                "sha256": _payload_sha(events),
                "input_status": "complete",
            },
            {
                "path": "git_facts.json",
                "source_type": "git",
                "source_uri": "fixture://kubernetes-demo/git-facts",
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
                "contract_id": "contract:k8s-kep-approval:v1",
                "contract_kind": "contiguous_sequence",
                "sequence_key": "k8s-kep-approval",
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
                "source_uri": "fixture://kubernetes-demo/contracts/kep-approval",
                "content_sha256": EMPTY_SHA,
                "limitations": [
                    "Slack is a SIG-shaped mock unless --slack-dir points at a real export.",
                ],
            }
        ],
        "acceptance_labels": {
            "ghost_broker_key": "person:k8s-bridge-ops",
            "faultline_source_module_key": "module:network",
            "faultline_target_module_key": "module:api-machinery",
        },
        "limitations": [
            f"Dataset {DATASET_ID} is snapshot analytics over public Kubernetes org "
            f"governance + {repo_count} active repos (kubernetes + kubernetes-sigs), "
            "not a live HydraDB org connection.",
            "People come from sigs.yaml chairs/tech leads; not every org member.",
            "Repo→SIG ownership uses topic/name heuristics when OWNERS files are not parsed.",
            "Slack edges are SIG-shaped mocks unless a real Slack export is provided.",
            "Absence does not establish deletion. The corpus is structurally incomplete.",
        ],
    }


def _ground_truth(sig_meta: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ghost_broker_key": "person:k8s-bridge-ops",
        "faultline_source_module_key": "module:network",
        "faultline_target_module_key": "module:api-machinery",
        "missing_sequence_key": "k8s-kep-approval",
        "sig_count": len(sig_meta),
        "notes": [
            "K8s Bridge Ops is the load-bearing cross-SIG communicator despite IC rank.",
            "network → api-machinery is a primary coordination faultline.",
            "KEP approval step is missing between directive and code change.",
        ],
    }


def _write_export_maps(
    export_root: Path, people: list[dict[str, Any]], modules: list[dict[str, Any]]
) -> None:
    identity = {p["id"]: p["id"] for p in people}
    for person in people:
        identity[f"{person['id']}@users.noreply.github.com"] = person["id"]
        identity[f"@{person['id']}"] = person["id"]
    prefixes = {f"{m['key']}/": m["key"] for m in modules if m["kind"] == "sig"}
    prefixes.update({f"{m['key']}/": m["key"] for m in modules if m["kind"] == "repo"})
    _write_json(export_root / "identity.json", identity)
    _write_json(export_root / "modules.json", prefixes)
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
            for p in people
        ],
    )


def _write_mock_slack(
    slack_dir: Path, people: list[dict[str, Any]], sig_meta: list[dict[str, Any]]
) -> None:
    slack_dir.mkdir(parents=True, exist_ok=True)
    channels: list[dict[str, Any]] = []
    users = [
        {
            "id": f"U{_slug(p['id']).upper()[:8]}",
            "name": p["id"],
            "real_name": p["display_name"],
            "profile": {"display_name": p["display_name"], "real_name": p["display_name"]},
        }
        for p in people
    ]
    user_by_handle = {p["id"]: f"U{_slug(p['id']).upper()[:8]}" for p in people}
    _write_json(slack_dir / "users.json", users)

    ts = float(COMM_EPOCH)
    for idx, sig in enumerate(sig_meta):
        channel = re.sub(r"[^a-z0-9-]", "-", sig["slack"].lower())[:40] or f"sig-{sig['slug']}"
        channel_dir = slack_dir / channel
        channel_dir.mkdir(parents=True, exist_ok=True)
        members = [user_by_handle[p["id"]] for p in people if p["team_key"] == f"team:{sig['slug']}"]
        if "k8s-bridge-ops" in user_by_handle:
            members.append(user_by_handle["k8s-bridge-ops"])
        channels.append(
            {
                "id": f"C{idx:04d}K8S",
                "name": channel,
                "created": EPOCH,
                "creator": members[0] if members else "UBRIDGE",
                "is_archived": False,
                "is_general": False,
                "members": members,
                "topic": {"value": f"{sig['label']} coordination"},
                "purpose": {"value": "Mock SIG Slack until a real CNCF Slack export is provided"},
            }
        )
        messages: list[dict[str, Any]] = []
        chairs = [c for c in sig["chairs"] if c in user_by_handle]
        scripts: list[tuple[str, str]] = []
        if "k8s-bridge-ops" in user_by_handle:
            scripts.append(
                ("k8s-bridge-ops", f"Need eyes from {sig['label']} on the cross-SIG API change.")
            )
        for chair in chairs[:2]:
            scripts.append((chair, f"Tracking {sig['slug']} OWNERS review load this week."))
        if "k8s-bridge-ops" in user_by_handle and chairs:
            scripts.append(
                (
                    "k8s-bridge-ops",
                    f"@{chairs[0]} can we sync with api-machinery before the KEP freeze?",
                )
            )
        for handle, text in scripts:
            messages.append(
                {
                    "type": "message",
                    "user": user_by_handle[handle],
                    "text": text,
                    "ts": f"{ts:.6f}",
                }
            )
            ts += 90.0
        _write_json(channel_dir / "2025-01-15.json", messages)
    _write_json(slack_dir / "channels.json", channels)


def _fetch_github_issues(
    out_path: Path, *, limit: int, repos: list[dict[str, Any]]
) -> None:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    targets = [r for r in repos if r["org"] == "kubernetes"][:6]
    if not targets:
        targets = repos[:6]
    issues: list[dict[str, Any]] = []
    per_repo = max(20, limit // max(1, len(targets)))
    for repo in targets:
        page = 1
        got = 0
        while got < per_repo and len(issues) < limit:
            url = (
                f"https://api.github.com/repos/{repo['full_name']}/issues"
                f"?state=all&per_page=50&page={page}"
            )
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    batch = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                print(f"GitHub issues {repo['full_name']}: HTTP {exc.code}")
                break
            if not isinstance(batch, list) or not batch:
                break
            for item in batch:
                if "pull_request" in item:
                    continue
                item["_repo"] = repo["full_name"]
                issues.append(item)
                got += 1
                if got >= per_repo or len(issues) >= limit:
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
        "repository",
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
                    "repository": item.get("_repo"),
                }
            )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", value.strip().lower()).strip("-")


def _payload_sha(rows: list[dict[str, Any]]) -> str:
    blob = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
