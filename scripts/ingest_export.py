"""Ingest real exports (mbox, JIRA CSV, git log, Slack export) into an X-Ray snapshot.

Everything is deterministic and offline. People are resolved through an explicit
identity map; unmapped ids become visible ``unresolved-…`` handles with a bundle
limitation rather than a failure. Nothing here talks to HydraDB — the resulting
snapshot directory is what the API seeds via ``POST /api/v1/hydra/seed-fixture``
(``XRAY_SNAPSHOT_DIR``) or what the loader reads directly.

Example (Apache-style public corpus):

    uv run python scripts/ingest_export.py \\
        --dataset-id kafka-2025q2 \\
        --directory data/exports/kafka/directory.json \\
        --identity-map data/exports/kafka/identity.json \\
        --mbox data/exports/kafka/dev.mbox \\
        --jira-csv data/exports/kafka/jira.csv \\
        --git-log data/exports/kafka/git.log --module-prefixes data/exports/kafka/modules.json \\
        --out data/snapshots/kafka-2025q2

Produce ``git.log`` with:

    git log --name-only --format="%x1e%H%x1f%at%x1f%ae%x1f%s%x1f%b" > git.log
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_ingest.adapters import git_log_rows, jira_csv_rows, mbox_rows, slack_export_rows
from xray_ingest.manifest import write_snapshot
from xray_ingest.pipeline import ingest_exports


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    directory = _load_records(Path(args.directory))
    identity_map = _load_mapping(args.identity_map)
    module_prefixes = _load_mapping(args.module_prefixes)
    channel_modules = _load_module_lists(args.channel_modules)
    message_modules = _load_module_lists(args.message_modules)
    contracts = _load_contracts(args.contracts)

    email_rows = (
        mbox_rows(
            [Path(item) for item in args.mbox],
            module_keys_by_message_id=message_modules,
            ignore_addresses=_load_list(args.ignore_addresses),
            skip_senders=_load_list(args.skip_senders),
        )
        if args.mbox
        else ()
    )
    ticket_rows = jira_csv_rows(Path(args.jira_csv)) if args.jira_csv else ()
    git_rows = (
        git_log_rows(Path(args.git_log), module_prefixes=module_prefixes) if args.git_log else ()
    )
    slack_rows = (
        slack_export_rows(Path(args.slack_dir), module_keys_by_channel=channel_modules)
        if args.slack_dir
        else ()
    )

    bundle = ingest_exports(
        directory_records=directory,
        contracts=contracts,
        dataset_id=args.dataset_id,
        slack_rows=slack_rows,
        email_rows=email_rows,
        ticket_rows=ticket_rows,
        git_rows=git_rows,
        identity_map=identity_map,
    )

    out = Path(args.out)
    manifest = write_snapshot(bundle, out)
    people = sum(1 for node in bundle.nodes if node.label == "Person")
    unresolved = sum(
        1
        for node in bundle.nodes
        if node.label == "Person" and node.properties.get("identity_status") == "unresolved"
    )
    print(f"Wrote snapshot {manifest.snapshot_id} to {out}")
    print(
        f"  nodes={len(bundle.nodes)} edges={len(bundle.edges)} evidence={len(bundle.evidence)} "
        f"people={people} unresolved_identities={unresolved}"
    )
    print(
        f"  rows: email={len(email_rows)} tickets={len(ticket_rows)} "
        f"git={len(git_rows)} slack={len(slack_rows)}"
    )
    for limitation in bundle.limitations:
        print(f"  limitation: {limitation}")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--out", required=True, help="Snapshot output directory")
    parser.add_argument(
        "--directory",
        required=True,
        help="JSON list of canonical records: directory_person / directory_team / module",
    )
    parser.add_argument("--identity-map", help="JSON object: source id (email, Slack id) -> handle")
    parser.add_argument("--contracts", help="JSON with sequence_contracts + limitations (optional)")
    parser.add_argument(
        "--mbox", action="append", help="mbox file (repeatable; mailing list / mailbox export)"
    )
    parser.add_argument("--ignore-addresses", help="JSON list of list addresses to drop from To/Cc")
    parser.add_argument("--skip-senders", help="JSON list of automated senders to exclude")
    parser.add_argument("--message-modules", help="JSON object: Message-ID -> [module keys]")
    parser.add_argument("--jira-csv", help="JIRA CSV export")
    parser.add_argument("--git-log", help="git log output (see module docstring for the format)")
    parser.add_argument("--module-prefixes", help="JSON object: path prefix -> module key")
    parser.add_argument("--slack-dir", help="Slack export directory (one folder per channel)")
    parser.add_argument("--channel-modules", help="JSON object: channel -> [module keys]")
    args = parser.parse_args(argv)
    if not any((args.mbox, args.jira_csv, args.git_log, args.slack_dir)):
        parser.error("provide at least one of --mbox, --jira-csv, --git-log, --slack-dir")
    if args.git_log and not args.module_prefixes:
        parser.error("--git-log requires --module-prefixes")
    return args


def _load_records(path: Path) -> tuple[CanonicalRecord, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"{path} must contain a JSON list of canonical records")
    return tuple(CanonicalRecord.model_validate(item) for item in payload)


def _load_mapping(path: str | None) -> dict[str, str]:
    if path is None:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in payload.items()
    ):
        raise SystemExit(f"{path} must be a JSON object of string -> string")
    return dict(payload)


def _load_list(path: str | None) -> tuple[str, ...]:
    if path is None:
        return ()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        raise SystemExit(f"{path} must be a JSON list of strings")
    return tuple(payload)


def _load_module_lists(path: str | None) -> dict[str, tuple[str, ...]]:
    if path is None:
        return {}
    payload: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must be a JSON object of string -> [string]")
    result: dict[str, tuple[str, ...]] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, list):
            raise SystemExit(f"{path} must be a JSON object of string -> [string]")
        result[key] = tuple(str(item) for item in value)
    return result


def _load_contracts(path: str | None) -> SequenceContractSet:
    if path is None:
        return SequenceContractSet()
    payload: Mapping[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return SequenceContractSet.model_validate(
        {
            "contracts": payload.get("sequence_contracts", payload.get("contracts", [])),
            "limitations": payload.get("limitations", []),
        }
    )


if __name__ == "__main__":
    sys.exit(main())
