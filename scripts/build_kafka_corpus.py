"""Build the Apache Kafka real-corpus inputs for ``scripts/ingest_export.py``.

Inputs (all public, all downloaded by the user, none vendored):

* ``dev-YYYY-MM.mbox``   — https://lists.apache.org/api/mbox.lua?list=dev@kafka.apache.org&date=YYYY-MM
* ``git.log``            — ``git log --name-only --format="%x1e%H%x1f%at%x1f%ae%x1f%s%x1f%b"``
                           plus ``git-authors.txt`` = ``git log --format="%an%x1f%ae"``
* ``jira-all.csv``       — JIRA "all fields" CSV export for ``project=KAFKA``
* ``whimsy-projects.json`` — https://whimsy.apache.org/public/public_ldap_projects.json
                           (public roster: PMC members = ``owners``, committers = ``members``)

Outputs written next to the inputs:

* ``directory.json``  — canonical ``directory_person`` + ``module`` records
* ``identity.json``   — source id (email address / JIRA username) → handle
* ``modules.json``    — path prefix → module key
* ``skip-senders.json`` / ``ignore-addresses.json`` — automated relays and list addresses

Identity resolution is deliberately conservative and offline: a handle is the ASF id when an
``@apache.org`` address or roster membership is known, otherwise the most frequent email's
local part. Two source ids merge only on an **exact** match of ASF id, email address, or
case-folded display name. Nothing fuzzy, nothing that touches HydraDB.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mailbox
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from email.header import decode_header, make_header
from email.utils import getaddresses
from pathlib import Path
from typing import Any

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

# Formal seniority from the public ASF roster (spec §3.1 scale: 1=IC … 6=VP+).
ROLE_PMC = 4
ROLE_COMMITTER = 3
ROLE_CONTRIBUTOR = 1

BOT_SENDERS = {
    "jira@apache.org",
    "jenkins@builds.apache.org",
    "git@apache.org",
    "github@apache.org",
    "noreply@github.com",
    "notifications@github.com",
    "dev@kafka.apache.org",
}
LIST_ADDRESSES = {
    "dev@kafka.apache.org",
    "users@kafka.apache.org",
    "commits@kafka.apache.org",
    "jira@kafka.apache.org",
    "dev@kafka.apache.org.invalid",
}

# Kafka top-level source directories that are meaningful modules.
MODULE_PREFIXES = {
    "clients": "clients",
    "core": "core",
    "streams": "streams",
    "connect": "connect",
    "raft": "raft",
    "metadata": "metadata",
    "storage": "storage",
    "server": "server",
    "server-common": "server-common",
    "group-coordinator": "group-coordinator",
    "coordinator-common": "coordinator-common",
    "share-coordinator": "share-coordinator",
    "transaction-coordinator": "transaction-coordinator",
    "tools": "tools",
    "trogdor": "trogdor",
    "shell": "shell",
    "generator": "generator",
    "test-common": "test-common",
    "tests": "system-tests",
    "docs": "docs",
    "build.gradle": "build",
    "gradle": "build",
    "checkstyle": "build",
    "jmh-benchmarks": "jmh-benchmarks",
    "examples": "examples",
    "docker": "docker",
    "committer-tools": "committer-tools",
    "api-checker": "api-checker",
}


def main() -> int:
    args = _parse_args()
    root = Path(args.root)
    roster = _roster(root / "whimsy-projects.json", project=args.project)
    roster_names = _roster_names(root / "whimsy-people.json", roster)
    people = _People(roster, roster_names)

    for path in sorted(root.glob("dev-*.mbox")):
        for message in mailbox.mbox(path):
            for name, address in getaddresses(message.get_all("from", ())):
                address = _norm_email(address)
                if address and address not in BOT_SENDERS and address not in LIST_ADDRESSES:
                    people.observe(name=name, email=address, source="mail")

    authors_path = root / "git-authors.txt"
    if authors_path.exists():
        for line in authors_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "\x1f" not in line:
                continue
            name, email = line.split("\x1f", 1)
            people.observe(name=name, email=_norm_email(email), source="git")

    jira_path = root / "jira-all.csv"
    if jira_path.exists():
        with jira_path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                for field in ("Reporter", "Assignee", "Creator"):
                    username = (row.get(field) or "").strip()
                    if username:
                        people.observe(name=None, email=None, jira=username, source="jira")

    directory, identity = people.resolve()
    directory.extend(_module_records())

    _write_json(root / "directory.json", directory)
    _write_json(root / "identity.json", identity)
    _write_json(root / "modules.json", MODULE_PREFIXES)
    _write_json(root / "skip-senders.json", sorted(BOT_SENDERS))
    _write_json(root / "ignore-addresses.json", sorted(LIST_ADDRESSES))

    persons = [r for r in directory if r["kind"] == "directory_person"]
    by_role = Counter(r["metadata"]["role_rank"] for r in persons)
    print(f"people={len(persons)} identities={len(identity)} modules={len(MODULE_PREFIXES)}")
    print(
        f"role_rank distribution (4=PMC,3=committer,1=contributor): {dict(sorted(by_role.items()))}"
    )
    return 0


class _People:
    """Exact-match identity clustering across mail, git, and JIRA."""

    def __init__(self, roster: dict[str, int], roster_names: dict[str, str] | None = None) -> None:
        self.roster = roster  # asf id -> role_rank
        self.roster_names = roster_names or {}  # normalized public name -> asf id
        self.emails: Counter[str] = Counter()
        self.names_by_email: dict[str, Counter[str]] = defaultdict(Counter)
        self.emails_by_name: dict[str, set[str]] = defaultdict(set)
        self.display_names: dict[str, str] = {}  # normalized name -> best decoded display
        self.jira: Counter[str] = Counter()

    def observe(
        self, *, name: str | None, email: str | None, source: str, jira: str | None = None
    ) -> None:
        if jira:
            self.jira[jira.lower()] += 1
        if email:
            self.emails[email] += 1
            key = _norm_name(name)
            if key:
                self.names_by_email[email][key] += 1
                self.emails_by_name[key].add(email)
                decoded = _decode_name(name).strip()
                if decoded and (
                    key not in self.display_names or len(decoded) > len(self.display_names[key])
                ):
                    self.display_names[key] = decoded

    def resolve(self) -> tuple[list[dict[str, Any]], dict[str, str]]:
        # Union-find over emails: same normalized display name → same person.
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            parent[find(a)] = find(b)

        for email in self.emails:
            find(email)
        for _name, emails in self.emails_by_name.items():
            emails_list = sorted(emails)
            for other in emails_list[1:]:
                union(emails_list[0], other)

        clusters: dict[str, list[str]] = defaultdict(list)
        for email in self.emails:
            clusters[find(email)].append(email)

        identity: dict[str, str] = {}
        directory: list[dict[str, Any]] = []
        used_handles: set[str] = set()

        for _root, emails in sorted(clusters.items()):
            emails.sort(key=lambda e: (-self.emails[e], e))
            asf_ids = [e.split("@", 1)[0] for e in emails if e.endswith("@apache.org")]
            if not asf_ids:
                # Exact join on the roster member's public ASF name (no fuzzy matching).
                cluster_names = Counter()
                for email in emails:
                    cluster_names.update(self.names_by_email[email])
                for name, _count in cluster_names.most_common():
                    if name in self.roster_names:
                        asf_ids = [self.roster_names[name]]
                        break
            handle = asf_ids[0] if asf_ids else emails[0].split("@", 1)[0]
            handle = _safe_handle(handle)
            if handle in used_handles:
                # Two clusters resolved to the same id (e.g. jsancio@apache.org and
                # jsancio@company.com): an exact id match is stronger evidence than the
                # missing name join, so merge into the existing person.
                for email in emails:
                    identity[email] = handle
                continue
            used_handles.add(handle)
            for email in emails:
                identity[email] = handle
            # JIRA usernames are ASF ids; join on the exact handle.
            if handle in self.jira:
                identity[handle] = handle
            names = Counter()
            for email in emails:
                names.update(self.names_by_email[email])
            display = (
                self.display_names.get(names.most_common(1)[0][0], handle) if names else handle
            )
            directory.append(
                _person_record(handle, display, self.roster.get(handle, ROLE_CONTRIBUTOR), emails)
            )

        # JIRA-only usernames (no email seen anywhere) become their own handles.
        for username in sorted(self.jira):
            if username in identity:
                continue
            handle = _safe_handle(username)
            if handle in used_handles:
                continue
            used_handles.add(handle)
            identity[username] = handle
            directory.append(
                _person_record(handle, username, self.roster.get(handle, ROLE_CONTRIBUTOR), ())
            )
        return directory, identity


def _person_record(
    handle: str, display: str, role_rank: int, emails: Iterable[str]
) -> dict[str, Any]:
    return {
        "source": "kafka-directory",
        "external_id": handle,
        "kind": "directory_person",
        "occurred_at_epoch": 1735689600,
        "author_external_id": None,
        "parent_external_id": None,
        "subjects": [f"person:{handle}"],
        "content_sha256": EMPTY_SHA256,
        "content": None,
        "metadata": {
            "display_name": display,
            "role_rank": role_rank,
            "team_key": "team:apache-kafka",
            "source_identity_count": len(list(emails)),
        },
    }


def _module_records() -> list[dict[str, Any]]:
    records = []
    for module in sorted(set(MODULE_PREFIXES.values())):
        records.append(
            {
                "source": "kafka-directory",
                "external_id": module,
                "kind": "module",
                "occurred_at_epoch": 1735689600,
                "author_external_id": None,
                "parent_external_id": None,
                "subjects": [f"module:{module}"],
                "content_sha256": EMPTY_SHA256,
                "content": None,
                "metadata": {"canonical_key": f"module:{module}", "criticality": 1.0},
            }
        )
    return records


def _roster(path: Path, *, project: str) -> dict[str, int]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    entry = payload.get("projects", {}).get(project, {})
    roles = {member.lower(): ROLE_COMMITTER for member in entry.get("members", [])}
    roles.update({owner.lower(): ROLE_PMC for owner in entry.get("owners", [])})
    return roles


def _roster_names(path: Path, roster: dict[str, int]) -> dict[str, str]:
    """Normalized public name -> ASF id, for roster members only (public_ldap_people.json)."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    people = payload.get("people", {})
    names: dict[str, str] = {}
    for asf_id in roster:
        name = _norm_name(str(people.get(asf_id, {}).get("name", "")))
        if name and name not in names:
            names[name] = asf_id
    return names


def _norm_email(value: str) -> str:
    cleaned = value.strip().strip("<>").lower()
    return cleaned.removesuffix(".invalid")


def _decode_name(value: str | None) -> str:
    """Decode RFC 2047 encoded-words (=?utf-8?b?...?=) into a plain string."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # malformed header: keep the raw text
        return value


def _norm_name(value: str | None) -> str:
    if not value:
        return ""
    decoded = _decode_name(value)
    # Fold accents (José -> Jose) so the same person joins across sources; still exact.
    folded = unicodedata.normalize("NFKD", decoded).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"\(.*?\)", "", folded)  # drop "(via GitHub)" etc.
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", cleaned.lower())
    parts = [p for p in cleaned.split() if p]
    if len(parts) < 2:
        return ""  # single tokens ("Chia") are too ambiguous to merge on
    return " ".join(parts)


def _safe_handle(value: str) -> str:
    handle = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-.")
    return handle or "person"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", default="data/exports/kafka")
    parser.add_argument("--project", default="kafka")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
