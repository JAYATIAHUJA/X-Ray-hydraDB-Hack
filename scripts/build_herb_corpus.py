"""Build an X-Ray snapshot from Salesforce HERB — the official Track 01 corpus.

Downloads (or reads locally) ``metadata/employee.json``, ``metadata/salesforce_team.json``
and N product files from ``huggingface.co/datasets/Salesforce/HERB``, runs them through
``xray_ingest.adapters.herb`` and the same ``ingest_exports`` pipeline every other source
uses, and writes a snapshot directory the API can serve.

    uv run python scripts/build_herb_corpus.py --products 6 --out data/snapshots/herb-6
    uv run python scripts/build_herb_corpus.py --all      --out data/snapshots/herb-all

Nothing here is vendored: HERB is CC-BY-NC-4.0 and is fetched at build time into
``data/exports/herb`` (gitignored). Pass ``--offline`` to reuse what is already there.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from xray_core.models import CanonicalRecord, SequenceContractSet
from xray_ingest.adapters import (
    herb_directory_records,
    herb_document_rows,
    herb_pr_rows,
    herb_product_name,
    herb_slack_rows,
)
from xray_ingest.manifest import write_snapshot
from xray_ingest.pipeline import ingest_exports

HF_BASE = "https://huggingface.co/datasets/Salesforce/HERB/resolve/main"
HF_TREE = "https://huggingface.co/api/datasets/Salesforce/HERB/tree/main/products"
METADATA = ("metadata/employee.json", "metadata/salesforce_team.json")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    export_dir = Path(args.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    products = _select_products(args, export_dir)
    if not args.offline:
        for rel in METADATA:
            _fetch(rel, export_dir / Path(rel).name)
        for name in products:
            _fetch(f"products/{name}.json", export_dir / f"{name}.json")

    product_paths = [export_dir / f"{name}.json" for name in products]
    missing = [p for p in product_paths if not p.exists()]
    if missing:
        raise SystemExit(f"missing product files: {[p.name for p in missing]} (drop --offline?)")

    directory_payload = herb_directory_records(
        export_dir / "employee.json",
        export_dir / "salesforce_team.json",
        [herb_product_name(p) for p in product_paths],
    )
    directory = tuple(CanonicalRecord.model_validate(item) for item in directory_payload)

    slack_rows: list[dict[str, object]] = []
    git_rows: list[dict[str, object]] = []
    ticket_rows: list[dict[str, object]] = []
    for path in product_paths:
        slack_rows.extend(herb_slack_rows(path))
        prs, reviews = herb_pr_rows(path)
        git_rows.extend(prs)
        slack_rows.extend(reviews)
        ticket_rows.extend(herb_document_rows(path))

    # eids are already directory handles; PR logins (EMP_…) have no HERB mapping and
    # deliberately stay unresolved so the limitation is visible, not hidden.
    identity_map: dict[str, str] = {}
    if args.identity_map:
        identity_map = json.loads(Path(args.identity_map).read_text(encoding="utf-8"))

    bundle = ingest_exports(
        directory_records=directory,
        contracts=SequenceContractSet(
            limitations=(
                "HERB Slack carries no thread metadata; reply edges come from PR reviews and explicit @mentions only.",
                "PR author logins (EMP_…) have no HERB mapping to employee ids and stay unresolved by design.",
            )
        ),
        dataset_id=args.dataset_id,
        slack_rows=tuple(slack_rows),
        email_rows=(),
        ticket_rows=tuple(ticket_rows),
        git_rows=tuple(git_rows),
        identity_map=identity_map,
    )
    out = Path(args.out)
    manifest = write_snapshot(bundle, out)
    people = sum(1 for n in bundle.nodes if n.label == "Person")
    unresolved = sum(
        1
        for n in bundle.nodes
        if n.label == "Person" and n.properties.get("identity_status") == "unresolved"
    )
    print(f"Wrote snapshot {manifest.snapshot_id} to {out}")
    print(f"  products={len(products)} {', '.join(products)}")
    print(
        f"  nodes={len(bundle.nodes)} edges={len(bundle.edges)} evidence={len(bundle.evidence)} "
        f"people={people} unresolved_identities={unresolved}"
    )
    print(f"  rows: slack={len(slack_rows)} prs={len(git_rows)} docs={len(ticket_rows)}")
    for limitation in bundle.limitations:
        print(f"  limitation: {limitation}")
    (out / "herb-products.json").write_text(json.dumps(products, indent=2), encoding="utf-8")
    return 0


def _select_products(args: argparse.Namespace, export_dir: Path) -> list[str]:
    if args.product:
        return list(dict.fromkeys(args.product))
    if args.offline:
        names = sorted(
            p.stem
            for p in export_dir.glob("*.json")
            if p.stem not in {"employee", "salesforce_team"}
        )
        return names if args.all else names[: args.products]
    with urllib.request.urlopen(HF_TREE, timeout=60) as response:
        tree = json.load(response)
    names = sorted(Path(item["path"]).stem for item in tree if item.get("type") == "file")
    return names if args.all else names[: args.products]


def _fetch(rel: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    url = f"{HF_BASE}/{rel}"
    print(f"  fetch {url}", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=120) as response:
        dest.write_bytes(response.read())


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", required=True, help="Snapshot output directory")
    parser.add_argument("--dataset-id", default="herb")
    parser.add_argument("--export-dir", default="data/exports/herb")
    parser.add_argument(
        "--products", type=int, default=6, help="How many product files (alphabetical)"
    )
    parser.add_argument("--product", action="append", help="Explicit product name (repeatable)")
    parser.add_argument("--all", action="store_true", help="All 30 products")
    parser.add_argument(
        "--offline", action="store_true", help="Do not download; use export-dir as-is"
    )
    parser.add_argument("--identity-map", help="Optional JSON: PR login -> eid")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
