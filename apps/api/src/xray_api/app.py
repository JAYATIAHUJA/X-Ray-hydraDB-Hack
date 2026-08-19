from __future__ import annotations

import json
import os
import secrets
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from xray_analytics import (
    FaultlineFinding,
    GapFinding,
    GhostScore,
    answer_ontology_question,
    communication_asymmetries,
    faultline_tier,
    faultlines,
    gap_findings,
    ghost_scores,
    shortest_communication_bridge,
)
from xray_core.models import (
    AnalysisStatus,
    CanonicalBundle,
    CanonicalRecord,
    EdgeRow,
    EvidenceRecord,
    NodeRow,
    SequenceContractSet,
)
from xray_core.paths import normalize_pair
from xray_hydra import HydraGateway
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

from .config import XraySettings, get_settings
from .dependencies import (
    FIXTURE_VARIANTS,
    SYNTH_DATASET_ID,
    active_bundle,
    demo_bundle,
    get_gateway,
    snapshot_dir,
    synth_bundle,
)
from .errors import not_found
from .hydra import (
    HydraGapRow,
    HydraGraphEdge,
    HydraGraphNode,
    HydraHealth,
    communication_distances,
    gap_rows,
    graph_rows,
    hydra_health,
    seed_bundle,
)
from .lenses import (
    client_ghost_baseline_ms,
    fixture_ghost_findings,
    fixture_what_if,
    live_gap_chain,
    live_ghost_findings,
)
from .schemas import (
    ActivateSnapshotRequest,
    AvailableSnapshot,
    EngineComparison,
    GapPathRequest,
    GraphEdge,
    GraphNode,
    GraphResponse,
    HealthResponse,
    HydraHealthResponse,
    HydraSeedResponse,
    ImportRequest,
    LensEnvelope,
    LoadReportResponse,
    QuestionRequest,
    QuestionResponse,
    SnapshotResponse,
    WhatIfSummary,
)

SettingsDep = Annotated[XraySettings, Depends(get_settings)]
GatewayDep = Annotated[HydraGateway | None, Depends(get_gateway)]
WriteToken = Annotated[str | None, Header(alias="X-Xray-Write-Token")]


@dataclass(frozen=True, slots=True)
class _SelectedSnapshot:
    bundle: CanonicalBundle
    kind: str
    name: str

    @property
    def snapshot_id(self) -> str:
        return f"{self.bundle.dataset_id}:{self.kind}"


class _SnapshotStore:
    """App-local snapshot selection; requests never mutate process environment."""

    def __init__(self) -> None:
        root = snapshot_dir()
        bundle = active_bundle()
        self._selection = _SelectedSnapshot(
            bundle=bundle,
            kind="snapshot" if root is not None else "fixture",
            name=root.name if root is not None else os.environ.get("XRAY_FIXTURE_VARIANT", "demo"),
        )
        self._lock = RLock()

    def current(self) -> _SelectedSnapshot:
        with self._lock:
            return self._selection

    def require(self, snapshot_id: str) -> CanonicalBundle:
        selected = self.current()
        if snapshot_id != selected.snapshot_id:
            raise not_found(f"Unknown snapshot {snapshot_id!r}", code="snapshot_not_found")
        return selected.bundle

    def activate_fixture(self, name: str) -> _SelectedSnapshot:
        bundle = synth_bundle() if FIXTURE_VARIANTS[name] == SYNTH_DATASET_ID else demo_bundle()
        return self._set(bundle=bundle, kind="fixture", name=name)

    def activate_snapshot(self, name: str, root: Path) -> _SelectedSnapshot:
        from .dependencies import snapshot_bundle

        return self._set(bundle=snapshot_bundle(str(root)), kind="snapshot", name=name)

    def activate_import(self, bundle: CanonicalBundle, root: Path) -> _SelectedSnapshot:
        return self._set(bundle=bundle, kind="snapshot", name=root.name)

    def _set(self, *, bundle: CanonicalBundle, kind: str, name: str) -> _SelectedSnapshot:
        selected = _SelectedSnapshot(bundle=bundle, kind=kind, name=name)
        with self._lock:
            self._selection = selected
        return selected


def create_app() -> FastAPI:
    app = FastAPI(title="X-Ray Evidence Platform API", version="0.1.0")
    snapshots = _SnapshotStore()
    # Extra origins for deployed frontends, comma-separated (the demo compose/Fly setup
    # proxies /api same-origin, so it needs none of this).
    extra_origins = [
        origin.strip()
        for origin in os.environ.get("XRAY_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", *extra_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["content-type"],
    )

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health(settings: SettingsDep) -> HealthResponse:
        hydra = hydra_health(settings, snapshots.current().bundle.dataset_id)
        return HealthResponse(
            status="ok",
            hydra=_hydra_health_response(hydra),
            read_only=settings.read_only,
            imports_enabled=settings.imports_enabled and not settings.read_only,
        )

    @app.post("/api/v1/hydra/seed-fixture", response_model=HydraSeedResponse)
    def seed_fixture(
        settings: SettingsDep,
        gateway: GatewayDep,
        write_token: WriteToken = None,
    ) -> HydraSeedResponse:
        _require_write_access(settings, write_token)
        result = seed_bundle(settings, snapshots.current().bundle, gateway=gateway)
        report = result.report
        return HydraSeedResponse(
            status=result.status,
            detail=result.detail,
            hydra=_hydra_health_response(result.hydra),
            report=None
            if report is None
            else LoadReportResponse(
                snapshot_id=report.snapshot_id,
                node_count=report.node_count,
                edge_count=report.edge_count,
                attempted_batches=report.attempted_batches,
                completed_batches=report.completed_batches,
                resumed_batches=report.resumed_batches,
                failed_batches=report.failed_batches,
                graph_fingerprint=report.graph_fingerprint,
            ),
        )

    @app.get("/api/v1/snapshots/current", response_model=SnapshotResponse)
    def current_snapshot() -> SnapshotResponse:
        return _snapshot_response(snapshots.current())

    @app.get("/api/v1/snapshots/available", response_model=tuple[AvailableSnapshot, ...])
    def available_snapshots() -> tuple[AvailableSnapshot, ...]:
        """Corpora that ship with the repo or were ingested into data/snapshots."""
        current = snapshots.current()
        items: list[AvailableSnapshot] = [
            AvailableSnapshot(
                name=key,
                kind="fixture",
                dataset_id=dataset,
                active=current.kind == "fixture" and current.name == key,
            )
            for key, dataset in FIXTURE_VARIANTS.items()
        ]
        for path in sorted(_snapshots_root().glob("*/manifest.json")):
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

    @app.post("/api/v1/snapshots/activate", response_model=SnapshotResponse)
    def activate_snapshot(
        request: ActivateSnapshotRequest,
        settings: SettingsDep,
        write_token: WriteToken = None,
    ) -> SnapshotResponse:
        """Switch the served corpus to a shipped fixture or an ingested snapshot.

        Only names under data/snapshots or the bundled fixture keys are accepted —
        this is a picker, not a path input.
        """
        _require_write_access(settings, write_token)
        if request.name in FIXTURE_VARIANTS:
            selected = snapshots.activate_fixture(request.name)
        else:
            candidate = _snapshots_root() / request.name
            if not (candidate / "manifest.json").is_file():
                raise HTTPException(status_code=404, detail=f"unknown snapshot {request.name!r}")
            selected = snapshots.activate_snapshot(request.name, candidate.resolve())
        return _snapshot_response(selected)

    @app.post("/api/v1/snapshots/import", response_model=SnapshotResponse)
    def import_snapshot(
        request: ImportRequest,
        settings: SettingsDep,
        write_token: WriteToken = None,
    ) -> SnapshotResponse:
        """Import browser-supplied export text and make the new snapshot active."""
        _require_write_access(settings, write_token, import_operation=True)
        directory = tuple(CanonicalRecord.model_validate(item) for item in request.directory)
        known_directory = tuple(record for record in directory if record.kind == "directory_person")
        contracts = SequenceContractSet()
        with tempfile.TemporaryDirectory(prefix="xray-import-input-") as input_dir:
            root = Path(input_dir)
            mbox_paths = []
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
            bundle = ingest_exports(
                directory_records=known_directory,
                canonical_records=tuple(
                    record for record in directory if record.kind != "directory_person"
                ),
                contracts=contracts,
                dataset_id=request.dataset_id,
                identity_map=request.identity_map,
                email_rows=mbox_rows(
                    mbox_paths,
                    module_keys_by_message_id=request.message_modules,
                )
                if mbox_paths
                else (),
                ticket_rows=(*jira_rows, *confluence_rows, *github_rows),
                git_rows=git_log_rows(git_path, module_prefixes=request.module_prefixes)
                if git_path is not None
                else (),
                slack_rows=slack_export_rows(
                    slack_dir,
                    module_keys_by_channel=request.channel_modules,
                )
                if request.slack_exports
                else (),
            )
        output_dir = Path(tempfile.mkdtemp(prefix="xray-import-snapshot-"))
        write_snapshot(bundle, output_dir)
        return _snapshot_response(snapshots.activate_import(bundle, output_dir))

    @app.get("/api/v1/snapshots/{snapshot_id}/risk-report", response_class=PlainTextResponse)
    def risk_report(snapshot_id: str) -> str:
        """Export the current evidence-backed findings as a portable Markdown report."""
        bundle = snapshots.require(snapshot_id)
        ghost_findings = fixture_ghost_findings(bundle)[:1]
        faultline_findings = faultlines(bundle)[:3]
        gap_findings_list = gap_findings(bundle)[:10]
        lines = [
            f"# X-Ray Risk Report: {bundle.dataset_id}",
            "",
            "Structural position, not performance. Absence in the corpus does not establish deletion.",
            "",
            "## Ghost",
        ]
        if ghost_findings:
            ghost = ghost_findings[0]
            lines.append(
                f"- {ghost['display_name']}: structural rank #{ghost['structural_rank']}, "
                f"formal rank #{ghost['formal_rank']}, rank gap {ghost['rank_gap']}."
            )
        else:
            lines.append("- No Ghost finding available.")
        lines.extend(["", "## Faultlines"])
        for finding in faultline_findings:
            lines.append(
                f"- `{finding.source_module_key}` -> `{finding.target_module_key}`; "
                f"owners `{finding.source_owner_key}` / `{finding.target_owner_key}`; "
                f"tier `{finding.tier}`, severity {finding.severity:.1f}."
            )
        lines.extend(["", "## Gaps"])
        for gap_finding in gap_findings_list:
            lines.append(
                f"- `{gap_finding.phantom_key}` ({gap_finding.expected_kind}, {gap_finding.reason}); "
                "absence does not establish deletion."
            )
        lines.extend(["", "## Limitations", *[f"- {item}" for item in bundle.limitations]])
        return "\n".join(lines) + "\n"

    @app.get("/api/v1/snapshots/{snapshot_id}/graph", response_model=GraphResponse)
    def graph(
        snapshot_id: str,
        settings: SettingsDep,
        gateway: GatewayDep,
        window_days: Annotated[int, Query(ge=0, le=3650)] = 0,
    ) -> GraphResponse:
        bundle = _window_bundle(snapshots.require(snapshot_id), window_days)
        ranked = ghost_scores(bundle)
        scores = {score.person_key: score for score in ranked}
        # Pre-select the story: the largest formal-vs-structural gap among the ten most
        # structurally central people (a low-centrality outlier is not the Ghost).
        selected_score = max(ranked[:10], key=lambda score: score.rank_gap, default=None)
        selected_key = None if selected_score is None else selected_score.person_key
        hydra_rows = graph_rows(settings, bundle, gateway=gateway)
        if hydra_rows is not None and hydra_rows.nodes:
            return GraphResponse(
                snapshot_id=snapshot_id,
                nodes=tuple(
                    _hydra_graph_node(row, scores.get(row.key), selected_key)
                    for row in hydra_rows.nodes
                ),
                edges=tuple(_hydra_graph_edge(edge) for edge in hydra_rows.edges),
            )

        people = tuple(
            sorted(
                (node for node in bundle.nodes if node.label == "Person"),
                key=lambda node: node.canonical_key,
            )
        )
        node_key_by_id = {node.id: node.canonical_key for node in people}

        return GraphResponse(
            snapshot_id=snapshot_id,
            nodes=tuple(
                _graph_node(node, scores.get(node.canonical_key), selected_key) for node in people
            ),
            edges=tuple(
                _graph_edge(edge, node_key_by_id)
                for edge in sorted(bundle.edges, key=lambda item: item.canonical_key)
                if edge.rel_type == "COMMUNICATES"
                and edge.source_id in node_key_by_id
                and edge.target_id in node_key_by_id
            ),
        )

    @app.get("/api/v1/snapshots/{snapshot_id}/ghosts", response_model=LensEnvelope)
    def ghosts(
        snapshot_id: str,
        settings: SettingsDep,
        gateway: GatewayDep,
        exclude: Annotated[list[str] | None, Query()] = None,
        window_days: Annotated[int, Query(ge=0, le=3650)] = 0,
    ) -> LensEnvelope:
        """Ghost lens. Pass ``?exclude=person:...`` (repeatable) for a what-if removal."""
        bundle = _window_bundle(snapshots.require(snapshot_id), window_days)
        excluded = _validated_person_keys(bundle, exclude or [])
        client_ms = client_ghost_baseline_ms(bundle)
        live_result = live_ghost_findings(
            settings, bundle, gateway=gateway, exclude_person_keys=excluded
        )
        if live_result is not None and live_result.error is None:
            comparison = EngineComparison(
                engine_ms=live_result.executed_query.engine_ms,
                client_ms=client_ms,
                client_method="python_bounded_bfs_all_pairs",
                sampled_people=live_result.sampled_people,
                engine_round_trips=live_result.executed_query.round_trips,
                client_equivalent_round_trips=_pairwise_round_trips(live_result.sampled_people),
            )
            return _lens_envelope(
                snapshot_id=snapshot_id,
                limitations=bundle.limitations,
                findings=_with_ghost_evidence(bundle, live_result.findings),
                explanation="HydraDB Ghost analysis completed with one bounded MSpaths sample call.",
                source="hydradb",
                executed_query=asdict(live_result.executed_query),
                what_if=None if live_result.what_if is None else asdict(live_result.what_if),
                comparison=comparison,
            )
        findings = fixture_ghost_findings(bundle, exclude_person_keys=excluded)
        people_count = sum(1 for node in bundle.nodes if node.label == "Person")
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=bundle.limitations,
            findings=_with_ghost_evidence(bundle, findings),
            explanation=(
                "HydraDB Ghost query degraded; fixture Ghost analysis completed with bounded in-memory path scoring."
                if live_result is not None
                else "Fixture Ghost analysis completed with bounded in-memory path scoring."
            ),
            status=AnalysisStatus.PARTIAL if live_result is not None else AnalysisStatus.COMPLETE,
            source="fixture" if live_result is None else "hydradb",
            degraded_reason=None if live_result is None else live_result.error,
            executed_query=None if live_result is None else asdict(live_result.executed_query),
            what_if=None if not excluded else asdict(fixture_what_if(bundle, excluded)),
            comparison=EngineComparison(
                engine_ms=None,
                client_ms=client_ms,
                client_method="python_bounded_bfs_all_pairs",
                sampled_people=people_count,
                engine_round_trips=0,
                client_equivalent_round_trips=_pairwise_round_trips(people_count),
            ),
        )

    @app.get("/api/v1/snapshots/{snapshot_id}/faultlines", response_model=LensEnvelope)
    def faultline_results(
        snapshot_id: str,
        settings: SettingsDep,
        gateway: GatewayDep,
        window_days: Annotated[int, Query(ge=0, le=3650)] = 0,
    ) -> LensEnvelope:
        bundle = _window_bundle(snapshots.require(snapshot_id), window_days)
        findings = faultlines(bundle)
        distance_result = communication_distances(
            settings,
            bundle,
            tuple((finding.source_owner_key, finding.target_owner_key) for finding in findings),
            gateway=gateway,
        )
        if distance_result is not None and distance_result.error is None:
            live_findings = tuple(
                _with_live_distance(finding, distance_result.distances) for finding in findings
            )
            findings = tuple(finding for finding in live_findings if finding.severity > 0)
            source = "hydradb"
            status = AnalysisStatus.COMPLETE
            degraded_reason = None
        elif distance_result is not None:
            source = "hydradb"
            status = AnalysisStatus.PARTIAL
            degraded_reason = distance_result.error
        else:
            source = "fixture"
            status = AnalysisStatus.COMPLETE
            degraded_reason = None
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=bundle.limitations,
            findings=_with_faultline_evidence(bundle, findings),
            explanation=(
                "HydraDB Faultline analysis completed with live owner communication distance queries."
                if source == "hydradb" and degraded_reason is None
                else "Fixture Faultline analysis completed over derived ownership and dependencies."
            ),
            status=status,
            source=source,
            degraded_reason=degraded_reason,
            executed_query=None
            if distance_result is None
            else {
                "text": distance_result.query.statement,
                "params": distance_result.query.parameters,
                "max_len": distance_result.query.max_len,
                "round_trips": 1,
                "engine_ms": distance_result.duration_ms,
            },
        )

    @app.get("/api/v1/snapshots/{snapshot_id}/gaps", response_model=LensEnvelope)
    def gaps(
        snapshot_id: str,
        settings: SettingsDep,
        gateway: GatewayDep,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> LensEnvelope:
        """All Phantom findings for the snapshot (no chain); use gap-paths for one chain."""
        bundle = snapshots.require(snapshot_id)
        live_gaps = gap_rows(settings, bundle, gateway=gateway)
        bundle_has_phantoms = any(node.label == "Phantom" for node in bundle.nodes)
        if live_gaps is not None and not live_gaps and bundle_has_phantoms:
            live_gaps = None
        all_findings = (
            tuple(_gap_finding_from_hydra(row) for row in live_gaps)
            if live_gaps is not None
            else gap_findings(bundle)
        )
        # Contract-declared missing steps first (they carry the strongest structural claim),
        # then in-window dangling parents (the corpus should contain them and does not),
        # then export-boundary ones (parent most likely predates the export); stable within
        # each group.
        ordered = sorted(
            all_findings,
            key=lambda f: (
                f.reason == "dangling_thread_parent",
                f.window_position == "export_boundary",
                -(f.days_after_corpus_start or 0),
                f.phantom_key,
            ),
        )
        in_window = sum(1 for f in all_findings if f.window_position == "in_window")
        boundary = sum(1 for f in all_findings if f.window_position == "export_boundary")
        position_note = (
            f" — {in_window} inside the export window, {boundary} at its boundary"
            if in_window or boundary
            else ""
        )
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=bundle.limitations,
            findings=_with_gap_evidence(bundle, tuple(ordered[:limit])),
            explanation=(
                f"{len(all_findings)} structurally missing records{position_note}"
                + (f" (showing {limit})" if len(all_findings) > limit else "")
                + ". Absence does not establish deletion."
            ),
            source="hydradb" if live_gaps is not None else "fixture",
            total_findings=len(all_findings),
        )

    @app.post("/api/v1/snapshots/{snapshot_id}/gap-paths", response_model=LensEnvelope)
    def gap_paths(
        snapshot_id: str,
        request: GapPathRequest,
        settings: SettingsDep,
        gateway: GatewayDep,
    ) -> LensEnvelope:
        bundle = snapshots.require(snapshot_id)
        live_chain = live_gap_chain(
            settings,
            bundle,
            source_artifact_key=request.source_artifact_key,
            target_artifact_key=request.target_artifact_key,
            gateway=gateway,
        )
        live_gaps = gap_rows(settings, bundle, gateway=gateway)
        bundle_has_phantoms = any(node.label == "Phantom" for node in bundle.nodes)
        if live_gaps is not None and not live_gaps and bundle_has_phantoms:
            # The engine answered but holds no phantom rows for this dataset (seed not
            # applied yet). Serve the bundle's findings and say so rather than an empty lens.
            live_gaps = None
        all_findings = (
            tuple(_gap_finding_from_hydra(row) for row in live_gaps)
            if live_gaps is not None
            else gap_findings(bundle)
        )
        findings = tuple(
            finding
            for finding in all_findings
            if (
                request.target_artifact_key in finding.predecessor_keys
                and request.source_artifact_key in finding.successor_keys
            )
        )
        chain: dict[str, object] | None = None
        if live_chain is not None and live_chain.error is None and live_chain.node_keys:
            phantom_keys = {node.canonical_key for node in bundle.nodes if node.label == "Phantom"}
            chain = {
                "node_keys": live_chain.node_keys,
                "phantom_indices": tuple(
                    index
                    for index, node_key in enumerate(live_chain.node_keys)
                    if node_key in phantom_keys
                ),
            }
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=bundle.limitations,
            findings=_with_gap_evidence(bundle, findings, chain=chain),
            explanation=(
                (
                    "HydraDB Gap analysis completed from live SPpaths and phantom lineage rows. "
                    if live_chain is not None and live_chain.error is None and live_gaps is not None
                    else "HydraDB Gap SPpaths query degraded; fixture gap filtering completed. "
                    if live_chain is not None and live_chain.error is not None
                    else "Fixture Gap analysis completed under explicit sequence contracts. "
                )
                + "Absence does not establish deletion."
            ),
            status=(
                AnalysisStatus.PARTIAL
                if live_chain is not None and live_chain.error is not None
                else AnalysisStatus.COMPLETE
            ),
            source="hydradb" if live_chain is not None or live_gaps is not None else "fixture",
            degraded_reason=None if live_chain is None else live_chain.error,
            executed_query=None if live_chain is None else asdict(live_chain.executed_query),
        )

    @app.post(
        "/api/v1/snapshots/{snapshot_id}/questions",
        response_model=QuestionResponse,
    )
    def answer_question(snapshot_id: str, request: QuestionRequest) -> QuestionResponse:
        answer = answer_ontology_question(snapshots.require(snapshot_id), request.question)
        return QuestionResponse(snapshot_id=snapshot_id, **asdict(answer))

    @app.get("/api/v1/snapshots/{snapshot_id}/asymmetries", response_model=LensEnvelope)
    def asymmetries(
        snapshot_id: str,
        min_replies: Annotated[int, Query(ge=1, le=1000)] = 3,
        min_ratio: Annotated[float, Query(gt=1, le=100)] = 3.0,
    ) -> LensEnvelope:
        bundle = snapshots.require(snapshot_id)
        findings = tuple(
            asdict(finding)
            for finding in communication_asymmetries(
                bundle, min_replies=min_replies, min_ratio=min_ratio
            )
        )
        return _lens_envelope(
            snapshot_id=snapshot_id,
            limitations=tuple(
                sorted(
                    {
                        *bundle.limitations,
                        "Reply asymmetry is a team-level coordination prompt, not an employee performance score.",
                    }
                )
            ),
            findings=findings,
            explanation=(
                "Directed reply flow is preserved. Findings mark strong send/receive imbalance "
                "and require team context before interpretation."
            ),
        )

    return app


def _snapshot_response(selected: _SelectedSnapshot) -> SnapshotResponse:
    bundle = selected.bundle
    return SnapshotResponse(
        snapshot_id=selected.snapshot_id,
        dataset_id=bundle.dataset_id,
        node_count=len(bundle.nodes),
        edge_count=len(bundle.edges),
        evidence_count=len(bundle.evidence),
        limitations=bundle.limitations,
    )


def _require_write_access(
    settings: XraySettings,
    supplied_token: str | None,
    *,
    import_operation: bool = False,
) -> None:
    if settings.read_only:
        raise HTTPException(status_code=403, detail="This deployment is read-only.")
    if import_operation and not settings.imports_enabled:
        raise HTTPException(
            status_code=403,
            detail="Snapshot imports are disabled; set XRAY_ENABLE_IMPORTS=true locally to opt in.",
        )
    if settings.write_token is not None and (
        supplied_token is None
        or not secrets.compare_digest(supplied_token, settings.write_token)
    ):
        raise HTTPException(status_code=401, detail="A valid X-Xray-Write-Token is required.")


def _write_optional_source(root: Path, name: str, content: str | None) -> Path | None:
    if content is None:
        return None
    path = root / name
    path.write_text(content, encoding="utf-8")
    return path


def _window_bundle(bundle: CanonicalBundle, window_days: int) -> CanonicalBundle:
    if window_days <= 0:
        return bundle
    observed_epochs = tuple(
        int(edge.properties["last_epoch"])
        for edge in bundle.edges
        if edge.rel_type == "COMMUNICATES"
        and type(edge.properties.get("last_epoch")) is int
    )
    if not observed_epochs:
        return bundle.model_copy(
            update={
                "limitations": tuple(
                    sorted(
                        {
                            *bundle.limitations,
                            f"The {window_days}-day communication window was not applied because no communication timestamps are available.",
                        }
                    )
                )
            }
        )
    reference_epoch = max(observed_epochs)
    cutoff = reference_epoch - (window_days * 86400)
    edges = tuple(
        edge
        for edge in bundle.edges
        if edge.rel_type != "COMMUNICATES"
        or (
            type(edge.properties.get("last_epoch")) is int
            and int(edge.properties["last_epoch"]) >= cutoff
        )
    )
    return bundle.model_copy(
        update={
            "edges": edges,
            "limitations": tuple(
                sorted(
                    {
                        *bundle.limitations,
                        f"Communication edges are filtered to the last {window_days} days ending at the latest observed communication ({reference_epoch}).",
                    }
                )
            ),
        }
    )


def _lens_envelope(
    *,
    snapshot_id: str,
    limitations: tuple[str, ...],
    findings: tuple[dict[str, object], ...],
    explanation: str,
    status: AnalysisStatus = AnalysisStatus.COMPLETE,
    source: str = "fixture",
    degraded_reason: str | None = None,
    executed_query: dict[str, object] | None = None,
    what_if: dict[str, object] | None = None,
    comparison: EngineComparison | None = None,
    total_findings: int | None = None,
) -> LensEnvelope:
    return LensEnvelope(
        snapshot_id=snapshot_id,
        analysis_status=status,
        status_explanation=explanation,
        limitations=limitations,
        findings=findings,
        source=source,
        degraded_reason=degraded_reason,
        executed_query=executed_query,
        what_if=None if what_if is None else WhatIfSummary.model_validate(what_if),
        comparison=comparison,
        total_findings=total_findings,
    )


def _validated_person_keys(bundle: CanonicalBundle, keys: list[str]) -> tuple[str, ...]:
    """Keep only keys that name people in the bundle; unknown keys are a 404, not a silent no-op."""
    people = {node.canonical_key for node in bundle.nodes if node.label == "Person"}
    unknown = sorted(key for key in keys if key not in people)
    if unknown:
        raise not_found(f"Unknown person keys: {', '.join(unknown)}", code="person_not_found")
    return tuple(sorted(set(keys)))


def _pairwise_round_trips(people: int) -> int:
    """Client-side equivalent of one pairwise MSpaths call: one shortest-path query per pair."""
    return people * (people - 1) // 2


def _with_ghost_evidence(
    bundle: CanonicalBundle, findings: tuple[dict[str, object], ...]
) -> tuple[dict[str, object], ...]:
    nodes = _nodes_by_key(bundle)
    evidence = _evidence_by_id(bundle)
    enriched: list[dict[str, object]] = []
    for finding in findings:
        person_key = finding.get("person_key")
        node = nodes.get(person_key) if isinstance(person_key, str) else None
        evidence_records = _evidence_summaries(evidence, () if node is None else node.evidence_ids)
        enriched.append({**finding, "evidence": evidence_records})
    return tuple(enriched)


def _with_faultline_evidence(
    bundle: CanonicalBundle, findings: tuple[FaultlineFinding, ...]
) -> tuple[dict[str, object], ...]:
    nodes = _nodes_by_key(bundle)
    edges = tuple(bundle.edges)
    evidence = _evidence_by_id(bundle)
    enriched: list[dict[str, object]] = []
    for finding in findings:
        dependency_evidence = _matching_edge_evidence_ids(
            edges,
            nodes,
            source_key=finding.source_module_key,
            target_key=finding.target_module_key,
            rel_type="DEPENDS_ON",
        )
        source_owner_evidence = _matching_edge_evidence_ids(
            edges,
            nodes,
            source_key=finding.source_owner_key,
            target_key=finding.source_module_key,
            rel_type="OWNS",
        )
        target_owner_evidence = _matching_edge_evidence_ids(
            edges,
            nodes,
            source_key=finding.target_owner_key,
            target_key=finding.target_module_key,
            rel_type="OWNS",
        )
        evidence_ids = tuple(
            dict.fromkeys((*dependency_evidence, *source_owner_evidence, *target_owner_evidence))
        )
        enriched.append(
            {
                **asdict(finding),
                "bridge": shortest_communication_bridge(
                    bundle,
                    finding.source_owner_key,
                    finding.target_owner_key,
                ),
                "evidence": _evidence_summaries(evidence, evidence_ids),
            }
        )
    return tuple(enriched)


def _snapshots_root() -> Path:
    """data/snapshots relative to the repo, overridable for deployments."""
    configured = os.environ.get("XRAY_SNAPSHOTS_ROOT", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).parents[4] / "data" / "snapshots"


def _with_gap_evidence(
    bundle: CanonicalBundle,
    findings: tuple[GapFinding, ...],
    *,
    chain: dict[str, object] | None = None,
) -> tuple[dict[str, object], ...]:
    nodes = _nodes_by_key(bundle)
    evidence = _evidence_by_id(bundle)
    enriched: list[dict[str, object]] = []
    for finding in findings:
        phantom = nodes.get(finding.phantom_key)
        evidence_records = _evidence_summaries(
            evidence, () if phantom is None else phantom.evidence_ids
        )
        enriched_finding = {**asdict(finding), "evidence": evidence_records}
        chain_node_keys = chain.get("node_keys", ()) if chain is not None else ()
        if (
            chain is not None
            and isinstance(chain_node_keys, tuple)
            and finding.phantom_key in chain_node_keys
        ):
            enriched_finding["chain"] = chain
        enriched.append(enriched_finding)
    return tuple(enriched)


def _nodes_by_key(bundle: CanonicalBundle) -> dict[str, NodeRow]:
    return {node.canonical_key: node for node in bundle.nodes}


def _evidence_by_id(bundle: CanonicalBundle) -> dict[str, EvidenceRecord]:
    return {record.evidence_id: record for record in bundle.evidence}


def _matching_edge_evidence_ids(
    edges: tuple[EdgeRow, ...],
    nodes: dict[str, NodeRow],
    *,
    source_key: str,
    target_key: str,
    rel_type: str,
) -> tuple[str, ...]:
    source = nodes.get(source_key)
    target = nodes.get(target_key)
    if source is None or target is None:
        return ()
    return tuple(
        evidence_id
        for edge in edges
        if edge.rel_type == rel_type and edge.source_id == source.id and edge.target_id == target.id
        for evidence_id in edge.evidence_ids
    )


def _evidence_summaries(
    evidence: dict[str, EvidenceRecord], evidence_ids: tuple[str, ...], *, limit: int = 4
) -> tuple[dict[str, object], ...]:
    records = tuple(
        evidence[evidence_id] for evidence_id in evidence_ids if evidence_id in evidence
    )
    return tuple(
        {
            "evidence_id": record.evidence_id,
            "source_type": record.source_type,
            "source_uri": record.source_uri,
            "source_record_id": record.source_record_id,
            "predicate": record.predicate,
            "subject_key": record.subject_key,
            "object_key": record.object_key,
            "evidence_class": record.evidence_class.value,
            "confidence": record.confidence,
            "content_sha256": record.content_sha256,
            "redacted_excerpt": record.redacted_excerpt,
        }
        for record in records[:limit]
    )


def _hydra_health_response(hydra: HydraHealth) -> HydraHealthResponse:
    return HydraHealthResponse(
        status=hydra.status,
        configured=hydra.configured,
        database=hydra.database,
        uri=hydra.uri,
        detail=hydra.detail,
        graph_loaded=hydra.graph_loaded,
        node_count=hydra.node_count,
        edge_count=hydra.edge_count,
    )


def _with_live_distance(
    finding: FaultlineFinding,
    distances: dict[tuple[str, str], int | None],
) -> FaultlineFinding:
    distance = distances.get(normalize_pair(finding.source_owner_key, finding.target_owner_key))
    tier, risk = faultline_tier(distance)
    return FaultlineFinding(
        source_module_key=finding.source_module_key,
        target_module_key=finding.target_module_key,
        source_owner_key=finding.source_owner_key,
        target_owner_key=finding.target_owner_key,
        dependency_weight=finding.dependency_weight,
        source_owner_confidence=finding.source_owner_confidence,
        target_owner_confidence=finding.target_owner_confidence,
        communication_distance=distance,
        tier=tier,
        severity=finding.dependency_weight * risk,
    )


def _gap_finding_from_hydra(row: HydraGapRow) -> GapFinding:
    expected_kind = row.properties.get("expected_kind")
    reason = row.properties.get("reason")
    inferred_epoch = row.properties.get("inferred_epoch")
    return GapFinding(
        phantom_key=row.phantom_key,
        expected_kind=expected_kind if isinstance(expected_kind, str) else "unknown",
        reason=reason if isinstance(reason, str) else "unknown",
        inferred_epoch=inferred_epoch if type(inferred_epoch) is int else None,
        predecessor_keys=row.predecessor_keys,
        successor_keys=row.successor_keys,
        window_position=(
            str(row.properties["window_position"])
            if isinstance(row.properties.get("window_position"), str)
            else "unknown"
        ),
        days_after_corpus_start=(
            int(row.properties["days_after_corpus_start"])
            if type(row.properties.get("days_after_corpus_start")) is int
            else None
        ),
    )


MIN_NODE_SIZE = 20
MAX_NODE_SIZE = 82


def _graph_node(node: NodeRow, score: GhostScore | None, selected_key: str | None) -> GraphNode:
    return _build_graph_node(node.canonical_key, node.properties, score, selected_key)


def _hydra_graph_node(
    node: HydraGraphNode, score: GhostScore | None, selected_key: str | None
) -> GraphNode:
    return _build_graph_node(node.key, node.properties, score, selected_key)


def _build_graph_node(
    key: str,
    properties: Mapping[str, object],
    score: GhostScore | None,
    selected_key: str | None,
) -> GraphNode:
    team = str(properties.get("team_id", "team:unknown")).removeprefix("team:")
    role_rank = _role_rank_value(properties.get("role_rank"))
    centrality = getattr(score, "sampled_centrality", 0.0)
    degree = getattr(score, "communication_degree", 0)
    return GraphNode(
        key=key,
        name=str(properties.get("display_name", key)),
        title=_person_title(team, role_rank),
        team=team,
        # Official size grows with formal seniority (spec §3.1: 1=IC … 6=VP+).
        official_size=max(MIN_NODE_SIZE, min(MAX_NODE_SIZE, 22 + (role_rank * 10))),
        actual_size=max(
            MIN_NODE_SIZE,
            min(MAX_NODE_SIZE, round(MIN_NODE_SIZE + (centrality * 250) + (degree * 3))),
        ),
        selected=key == selected_key,
    )


def _role_rank_value(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0


def _graph_edge(edge: EdgeRow, node_key_by_id: dict[int, str]) -> GraphEdge:
    weight = edge.properties.get("weight", 0)
    return GraphEdge(
        source=node_key_by_id[edge.source_id],
        target=node_key_by_id[edge.target_id],
        strength=_edge_strength(float(weight)),
    )


def _hydra_graph_edge(edge: HydraGraphEdge) -> GraphEdge:
    return GraphEdge(
        source=edge.source,
        target=edge.target,
        strength=_edge_strength(edge.weight),
    )


def _edge_strength(weight: float) -> str:
    if weight >= 5:
        return "strong"
    if weight >= 3:
        return "medium"
    return "weak"


ROLE_TITLES = {
    0: "member",
    1: "engineer",
    2: "senior engineer",
    3: "lead",
    4: "manager",
    5: "director",
}


def _person_title(team: str, role_rank: int) -> str:
    """Render a display title from the spec §3.1 role_rank scale (higher = more senior)."""
    team_name = team.replace("-", " ").capitalize()
    if role_rank >= 6:
        return f"VP, {team_name}"
    return f"{team_name} {ROLE_TITLES.get(role_rank, 'member')}"


app = create_app()


__all__ = ["app", "create_app"]
