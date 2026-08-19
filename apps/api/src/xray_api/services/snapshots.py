from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from xray_core.models import CanonicalBundle, CanonicalRecord
from xray_ingest.adapters import (
    confluence_xml_rows,
    git_log_rows,
    github_csv_rows,
    jira_csv_rows,
    mbox_rows,
    slack_export_rows,
)
from xray_ingest.manifest import write_snapshot
from xray_ingest.pipeline import ingest_exports

from ..dependencies import (
    FIXTURE_VARIANTS,
    SYNTH_DATASET_ID,
    active_bundle,
    demo_bundle,
    snapshot_bundle,
    snapshot_dir,
    synth_bundle,
)
from ..errors import not_found
from ..schemas import AvailableSnapshot, ImportRequest, SnapshotResponse


@dataclass(frozen=True, slots=True)
class SelectedSnapshot:
    bundle: CanonicalBundle
    kind: str
    name: str

    @property
    def snapshot_id(self) -> str:
        return f"{self.bundle.dataset_id}:{self.kind}"


class SnapshotService:
    """Own snapshot discovery, selection, and browser-export ingestion."""

    def __init__(self) -> None:
        root = snapshot_dir()
        bundle = active_bundle()
        self._selection = SelectedSnapshot(
            bundle=bundle,
            kind="snapshot" if root is not None else "fixture",
            name=root.name if root is not None else os.environ.get("XRAY_FIXTURE_VARIANT", "demo"),
        )
        self._lock = RLock()

    def current(self) -> SelectedSnapshot:
        with self._lock:
            return self._selection

    def require(self, snapshot_id: str) -> CanonicalBundle:
        selected = self.current()
        if snapshot_id != selected.snapshot_id:
            raise not_found(f"Unknown snapshot {snapshot_id!r}", code="snapshot_not_found")
        return selected.bundle

    def available(self) -> tuple[AvailableSnapshot, ...]:
        current = self.current()
        items = [
            AvailableSnapshot(
                name=key,
                kind="fixture",
                dataset_id=dataset,
                active=current.kind == "fixture" and current.name == key,
            )
            for key, dataset in FIXTURE_VARIANTS.items()
        ]
        for path in sorted(snapshots_root().glob("*/manifest.json")):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            items.append(
                AvailableSnapshot(
                    name=path.parent.name,
                    kind="snapshot",
                    dataset_id=str(manifest.get("dataset_id") or path.parent.name),
                    active=current.kind == "snapshot" and path.parent.name == current.name,
                )
            )
        return tuple(items)

    def activate(self, name: str) -> SelectedSnapshot:
        if name in FIXTURE_VARIANTS:
            bundle = synth_bundle() if FIXTURE_VARIANTS[name] == SYNTH_DATASET_ID else demo_bundle()
            return self._set(bundle=bundle, kind="fixture", name=name)
        candidate = snapshots_root() / name
        if not (candidate / "manifest.json").is_file():
            raise not_found(f"Unknown snapshot {name!r}", code="snapshot_not_found")
        return self._set(
            bundle=snapshot_bundle(str(candidate.resolve())),
            kind="snapshot",
            name=name,
        )

    def import_request(self, request: ImportRequest) -> SelectedSnapshot:
        bundle = _ingest_request(request)
        output_dir = Path(tempfile.mkdtemp(prefix="xray-import-snapshot-"))
        write_snapshot(bundle, output_dir)
        return self._set(bundle=bundle, kind="snapshot", name=output_dir.name)

    def response(self, selected: SelectedSnapshot | None = None) -> SnapshotResponse:
        value = selected or self.current()
        bundle = value.bundle
        return SnapshotResponse(
            snapshot_id=value.snapshot_id,
            dataset_id=bundle.dataset_id,
            node_count=len(bundle.nodes),
            edge_count=len(bundle.edges),
            evidence_count=len(bundle.evidence),
            limitations=bundle.limitations,
        )

    def _set(self, *, bundle: CanonicalBundle, kind: str, name: str) -> SelectedSnapshot:
        selected = SelectedSnapshot(bundle=bundle, kind=kind, name=name)
        with self._lock:
            self._selection = selected
        return selected


def snapshots_root() -> Path:
    configured = os.environ.get("XRAY_SNAPSHOTS_ROOT", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).parents[5] / "data" / "snapshots"


def _write_optional_source(root: Path, name: str, content: str | None) -> Path | None:
    if content is None:
        return None
    path = root / name
    path.write_text(content, encoding="utf-8")
    return path


def _ingest_request(request: ImportRequest) -> CanonicalBundle:
    directory = tuple(CanonicalRecord.model_validate(item) for item in request.directory)
    known_directory = tuple(record for record in directory if record.kind == "directory_person")
    with tempfile.TemporaryDirectory(prefix="xray-import-input-") as input_dir:
        root = Path(input_dir)
        mbox_paths: list[Path] = []
        for index, content in enumerate(request.mbox):
            path = root / f"mail-{index}.mbox"
            path.write_text(content, encoding="utf-8")
            mbox_paths.append(path)
        jira_path = _write_optional_source(root, "jira.csv", request.jira_csv)
        git_path = _write_optional_source(root, "git.log", request.git_log)
        confluence_path = _write_optional_source(root, "entities.xml", request.confluence_xml)
        github_path = _write_optional_source(root, "github-issues.csv", request.github_csv)
        slack_dir = root / "slack"
        slack_dir.mkdir()
        for channel, rows in request.slack_exports.items():
            (slack_dir / f"{channel}.json").write_text(json.dumps(list(rows)), encoding="utf-8")
        jira_rows = jira_csv_rows(jira_path) if jira_path is not None else ()
        confluence_rows = (
            confluence_xml_rows(confluence_path) if confluence_path is not None else ()
        )
        github_rows = github_csv_rows(github_path) if github_path is not None else ()
        return ingest_exports(
            directory_records=known_directory,
            canonical_records=tuple(
                record for record in directory if record.kind != "directory_person"
            ),
            contracts=request.sequence_contracts,
            dataset_id=request.dataset_id,
            identity_map=request.identity_map,
            email_rows=mbox_rows(mbox_paths, module_keys_by_message_id=request.message_modules)
            if mbox_paths
            else (),
            ticket_rows=(*jira_rows, *confluence_rows, *github_rows),
            git_rows=git_log_rows(git_path, module_prefixes=request.module_prefixes)
            if git_path is not None
            else (),
            slack_rows=slack_export_rows(slack_dir, module_keys_by_channel=request.channel_modules)
            if request.slack_exports
            else (),
        )


__all__ = ["SelectedSnapshot", "SnapshotService", "snapshots_root"]
