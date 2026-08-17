import cytoscape from "cytoscape";
import type { Core, ElementDefinition } from "cytoscape";
import { useEffect, useMemo, useRef, useState } from "react";
import type {
  EvidenceSummary,
  FaultlineFinding,
  GapFinding,
  GapPathRequest,
  GhostFinding,
  GraphEdge,
  GraphNode,
  LensEnvelope
} from "./api";
import { getRiskReport, importSnapshot } from "./api";
import type { ImportPayload } from "./api";
import type { Lens } from "./data";
import { useXraySnapshot } from "./queries";

const tabs: Array<{ id: Lens; label: string; sublabel: string; icon: string }> = [
  {
    id: "org",
    label: "Org",
    sublabel: "People & Structure",
    icon: "M8 3v4m0 0H5v4h6V7H8Zm0 0h8m0-4v4m0 0h-3v4h6V7h-3ZM8 15v-2m8 2v-2m-8 2H5v4h6v-4H8Zm8 0h-3v4h6v-4h-3Z"
  },
  {
    id: "faultlines",
    label: "Faultlines",
    sublabel: "Tension & Risk",
    icon: "M12 2 5 13h6l-1 9 7-12h-6l1-8Z"
  },
  {
    id: "gaps",
    label: "Gaps",
    sublabel: "Missing Links",
    icon: "M4 8V4h4m8 0h4v4M4 16v4h4m8 0h4v-4M9 9h6v6H9z"
  }
];

export function App() {
  const [activeLens, setActiveLens] = useState<Lens>("org");
  const [mode, setMode] = useState<"actual" | "official">("actual");
  const [selectedNodeKey, setSelectedNodeKey] = useState<string | undefined>();
  const [selectedFaultlineIndex, setSelectedFaultlineIndex] = useState(0);
  const [selectedGapIndex, setSelectedGapIndex] = useState(0);
  const [gapRequest, setGapRequest] = useState<GapPathRequest | undefined>();
  const [excluded, setExcluded] = useState<string[]>([]);
  const [windowDays, setWindowDays] = useState(0);
  const [reportStatus, setReportStatus] = useState<string | null>(null);
  const { faultlines, gapPath, gaps, ghosts, graph, health, snapshot } = useXraySnapshot(
    gapRequest,
    excluded,
    windowDays
  );
  const people = graph.data?.nodes ?? [];
  const defaultSelectedKey = people.find((person) => person.selected)?.key ?? people[0]?.key;
  const selectedKey = people.some((person) => person.key === selectedNodeKey) ? selectedNodeKey : defaultSelectedKey;
  const selected = people.find((person) => person.key === selectedKey);
  const ghostFinding = ghosts.data?.findings.find((finding) => finding.person_key === selected?.key);
  const faultlineFindings = faultlines.data?.findings ?? [];
  // The gap list comes from /gaps; the SPpaths chain for the selected one comes from /gap-paths.
  const gapList = gaps.data?.findings ?? [];
  const gapChainFinding = gapPath.data?.findings.find((finding) => finding.chain !== undefined);
  const gapFindings = gapList.map((finding) =>
    gapChainFinding && finding.phantom_key === gapChainFinding.phantom_key ? gapChainFinding : finding
  );
  const topGhost = ghosts.data?.findings[0];
  const largestGap = (ghosts.data?.findings ?? []).slice(0, 10).reduce<GhostFinding | undefined>(
    (best, finding) => (best === undefined || finding.rank_gap > best.rank_gap ? finding : best),
    undefined
  );
  const gapTotal = gaps.data?.total_findings ?? gapList.length;
  const connectedKeys = useMemo(() => {
    const keys = new Set<string>();
    (graph.data?.edges ?? []).forEach((edge) => {
      keys.add(edge.source);
      keys.add(edge.target);
    });
    return keys;
  }, [graph.data?.edges]);
  const faultlineOwnerKeys = useMemo(
    () => new Set(faultlineFindings.flatMap((f) => [f.source_owner_key, f.target_owner_key])),
    [faultlineFindings]
  );
  const hiddenIsolates = people.filter(
    (person) => !connectedKeys.has(person.key) && !faultlineOwnerKeys.has(person.key)
  ).length;
  const whatIf = ghosts.data?.what_if ?? null;
  const comparison = ghosts.data?.comparison ?? null;
  const selectedFaultline = faultlineFindings[selectedFaultlineIndex] ?? faultlineFindings[0];
  const selectedGap = gapFindings[selectedGapIndex] ?? gapFindings[0];
  const activeEnvelope = envelopeForLens(activeLens, ghosts.data, faultlines.data, gapPath.data ?? gaps.data);
  const activeQuery = activeEnvelope?.executed_query;

  async function exportRiskReport() {
    if (snapshot.data === undefined) return;
    setReportStatus("Preparing report");
    try {
      const report = await getRiskReport(snapshot.data.snapshot_id);
      const blob = new Blob([report], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${snapshot.data.dataset_id}-risk-report.md`;
      anchor.click();
      URL.revokeObjectURL(url);
      setReportStatus("Report downloaded");
    } catch {
      setReportStatus("Report unavailable");
    }
  }
  const queryErrors = [
    ["health", health.isError],
    ["snapshot", snapshot.isError],
    ["graph", graph.isError],
    ["ghost", ghosts.isError],
    ["faultlines", faultlines.isError],
    ["gaps", gaps.isError]
  ].filter(([, failed]) => failed);
  const hasError = queryErrors.length > 0;
  const isLoading =
    health.isPending ||
    snapshot.isPending ||
    graph.isPending ||
    ghosts.isPending ||
    faultlines.isPending ||
    gaps.isPending;
  const graphElements = useMemo(
    () =>
      graphElementsFor(
        people,
        graph.data?.edges ?? [],
        faultlineFindings,
        selectedFaultline,
        mode,
        selectedKey,
        excluded,
        connectedKeys
      ),
    [connectedKeys, excluded, faultlineFindings, graph.data?.edges, mode, people, selectedFaultline, selectedKey]
  );

  useEffect(() => {
    if (selectedNodeKey === undefined && defaultSelectedKey !== undefined) {
      setSelectedNodeKey(defaultSelectedKey);
    }
  }, [defaultSelectedKey, selectedNodeKey]);

  useEffect(() => {
    if (selectedFaultlineIndex >= faultlineFindings.length) {
      setSelectedFaultlineIndex(0);
    }
  }, [faultlineFindings.length, selectedFaultlineIndex]);

  useEffect(() => {
    if (selectedGapIndex >= gapFindings.length) {
      setSelectedGapIndex(0);
    }
  }, [gapFindings.length, selectedGapIndex]);

  useEffect(() => {
    const finding = gapList[selectedGapIndex];
    if (finding === undefined) {
      return;
    }
    const next = requestForGap(finding);
    if (
      next !== undefined &&
      (gapRequest === undefined ||
        gapRequest.source_artifact_key !== next.source_artifact_key ||
        gapRequest.target_artifact_key !== next.target_artifact_key)
    ) {
      setGapRequest(next);
    }
  }, [gapList, gapRequest, selectedGapIndex]);

  return (
    <main className="app-shell">
      <header className="topbar" aria-label="Application status">
        <div className="brand-mark" aria-hidden="true">
          X
        </div>
        <div>
          <h1>X-Ray</h1>
          <p>X-Ray Evidence Platform</p>
        </div>
        <div className="status-pill">{snapshot.data?.dataset_id ?? "fixture"}</div>
        <div className={hasError ? "topbar-metric unhealthy" : "topbar-metric healthy"}>
          {hasError ? `${queryErrors.map(([name]) => name).join(", ")} error` : isLoading ? "Loading" : "Healthy"}
        </div>
        <div className="topbar-metric">
          Graph: {snapshot.data?.node_count ?? "--"} nodes / {snapshot.data?.edge_count ?? "--"} edges
        </div>
        <div className={hydraStatusClass(health.data?.hydra.status)}>
          HydraDB: {formatHydraStatus(health.data?.hydra.status)}
          {health.data?.hydra.node_count !== null && health.data?.hydra.node_count !== undefined
            ? ` · ${health.data.hydra.node_count} nodes · ${health.data.hydra.edge_count ?? "--"} edges`
            : ""}
        </div>
      </header>

      <section className="hero-strip" aria-label="Snapshot summary">
        <button className="hero-tile" onClick={() => setActiveLens("org")} type="button" title="Ghost lens: person whose sampled betweenness centrality in the communication graph exceeds their formal seniority rank">
          <span>Load-bearing person</span>
          <strong>{topGhost?.display_name ?? "—"}</strong>
          <small>
            {topGhost
              ? largestGap && largestGap.person_key !== topGhost.person_key && largestGap.rank_gap > topGhost.rank_gap
                ? `structural #${topGhost.structural_rank} · formal #${topGhost.formal_rank} — largest gap: ${largestGap.display_name} #${largestGap.structural_rank} vs #${largestGap.formal_rank}`
                : `structural #${topGhost.structural_rank} · formal #${topGhost.formal_rank} · gap ${formatSignedRankGap(topGhost.rank_gap)}`
              : "waiting for Ghost lens"}
          </small>
        </button>
        <button className="hero-tile" onClick={() => setActiveLens("faultlines")} type="button" title="Faultline lens: module dependencies whose owners have no bounded communication path (≤4 hops) in the collaboration graph">
          <span>Uncoordinated dependencies</span>
          <strong>{faultlines.data ? faultlineFindings.length : "—"}</strong>
          <small>
            {faultlineFindings[0]
              ? `${suffix(faultlineFindings[0].source_module_key)} ↔ ${suffix(faultlineFindings[0].target_module_key)} · co-changed ${faultlineFindings[0].dependency_weight}× · no reply path`
              : "module pairs whose owners have no bounded path"}
          </small>
        </button>
        <button className="hero-tile" onClick={() => setActiveLens("gaps")} type="button" title="Gap lens: Phantom nodes the graph requires (via sequence contracts or dangling thread parents) but that are absent from the evidence corpus. Absence ≠ deletion.">
          <span>Structurally missing records</span>
          <strong>{gaps.data ? gapTotal : "—"}</strong>
          <small>
            {gaps.data
              ? `records the graph requires but the corpus lacks${gapTotal > gapList.length ? ` · showing ${gapList.length}` : ""}`
              : "phantom nodes required by the graph"}
          </small>
        </button>
        <div className="hero-tile hero-engine">
          <span>HydraDB vs client</span>
          <strong>
            {comparison?.engine_ms !== null && comparison?.engine_ms !== undefined
              ? `${comparison.engine_ms.toFixed(0)} ms`
              : "fixture mode"}
          </strong>
          <small>
            {comparison
              ? `1 MSpaths call replaces ${comparison.client_equivalent_round_trips.toLocaleString()} per-pair queries · Python BFS ${comparison.client_ms.toFixed(0)} ms`
              : "engine round trip vs in-process BFS"}
          </small>
        </div>
      </section>

      <ImportPanel />

      <div className="workspace">
        <aside className="rail" aria-label="Lens navigation">
          <nav>
            {tabs.map((tab) => (
              <button
                aria-current={activeLens === tab.id ? "page" : undefined}
                className={activeLens === tab.id ? "rail-item active" : "rail-item"}
                key={tab.id}
                onClick={() => setActiveLens(tab.id)}
                type="button"
              >
                <Icon path={tab.icon} />
                <span>{tab.label}</span>
                <small>{tab.sublabel}</small>
              </button>
            ))}
          </nav>
          <div className="rail-footer">
            <span>Mode</span>
            <strong>{activeEnvelope?.source ?? "fixture"}</strong>
          </div>
        </aside>

        <section className="canvas-panel" aria-label={`${activeLens} workspace`}>
          <div className="toolbar">
            <div className="segmented" role="group" aria-label="Node size mode">
              <button
                aria-pressed={mode === "official"}
                className={mode === "official" ? "segment active" : "segment"}
                onClick={() => setMode("official")}
                type="button"
              >
                Official
              </button>
              <button
                aria-pressed={mode === "actual"}
                className={mode === "actual" ? "segment active" : "segment"}
                onClick={() => setMode("actual")}
                type="button"
              >
                Actual
              </button>
            </div>
            <div className="scale">
              {mode === "official"
                ? "Node size = formal seniority (org chart)"
                : "Node size = sampled path centrality (who actually carries the work)"}
            </div>
            <div className="query-source">
              {activeEnvelope?.source ?? "fixture"} · {activeEnvelope?.analysis_status ?? "pending"}
            </div>
            <label className="window-control">
              Window
              <select value={windowDays} onChange={(event) => setWindowDays(Number(event.target.value))}>
                <option value={0}>All time</option>
                <option value={30}>30 days</option>
                <option value={90}>90 days</option>
                <option value={365}>365 days</option>
              </select>
            </label>
            <button className="report-button" onClick={exportRiskReport} type="button">
              Export report
            </button>
          </div>

          <div className="graph-stage" data-lens={activeLens}>
            {graph.isError ? <Notice text="Graph query failed. Other lens data can still render." tone="bad" /> : null}
            <CytoscapeGraph elements={graphElements} onSelect={setSelectedNodeKey} selectedKey={selectedKey} />
            <GraphLegend hiddenIsolates={hiddenIsolates} />
            {whatIf ? (
              <div className="what-if-banner" role="status">
                <strong>
                  Without {whatIf.excluded_person_keys.map((key) => nameFor(people, key)).join(", ")}:
                </strong>{" "}
                {whatIf.pairs_lost.toLocaleString()} of {whatIf.sampled_pairs_before.toLocaleString()} sampled
                pairs lose their ≤{whatIf.max_len}-hop path.
                <button onClick={() => setExcluded([])} type="button">
                  Restore
                </button>
              </div>
            ) : null}
          </div>

          <div className="bottom-grid">
            <DataTable
              emptyText={faultlines.isPending ? "Loading faultlines" : "No API faultlines"}
              onRowSelect={setSelectedFaultlineIndex}
              rows={toFaultlineRows(faultlineFindings)}
              selectedIndex={selectedFaultlineIndex}
              title="Faultlines"
            />
            <GapTimeline
              emptyText={gaps.isPending ? "Loading gaps" : "No structurally missing records in this snapshot."}
              findings={gapFindings}
              onSelect={setSelectedGapIndex}
              selectedIndex={selectedGapIndex}
              chainPending={gapPath.isPending && gapRequest !== undefined}
            />
          </div>
        </section>

        <aside className="detail-panel" aria-label="Selected finding details">
          <section className="selected-block">
            <span className="eyeline">Selected node</span>
            <h2>{selected?.name ?? "Loading graph"}</h2>
            <p>
              {selected?.title ?? "Waiting for graph"} / {selected?.team ?? "--"}
            </p>
            <code>{selected?.key ?? "--"}</code>
            {selected ? (
              <button
                className="what-if-button"
                disabled={excluded.includes(selected.key)}
                onClick={() => setExcluded([selected.key])}
                type="button"
              >
                {excluded.includes(selected.key) ? "Removed from the sample" : `What if ${selected.name} is out?`}
              </button>
            ) : null}
          </section>

          <section className="finding-block">
            <h3>Ghost</h3>
            <p>{ghosts.data?.status_explanation ?? "Waiting for fixture Ghost analysis."}</p>
            {ghostFinding === undefined && selected !== undefined ? (
              <p className="inline-warning">No ghost score for the selected person.</p>
            ) : null}
            {activeEnvelope?.degraded_reason ? <p className="inline-warning">{activeEnvelope.degraded_reason}</p> : null}
          </section>

          <section className="metric-grid">
            <Metric
              detail={`${ghostFinding?.structural_rank ?? "--"} structural rank`}
              label="Actual centrality"
              value={formatCentrality(ghostFinding)}
              tooltip="Sampled betweenness centrality: fraction of bounded (≤4-hop) shortest paths that pass through this person across the sampled communication graph. Higher = more load-bearing."
            />
            <Metric
              detail={`Formal rank: ${ghostFinding?.formal_rank ?? "--"}`}
              label="Rank gap"
              value={formatRankGap(ghostFinding)}
              tooltip="Structural rank minus formal rank. Positive = this person carries more coordination weight than their title suggests. Negative = formal authority without structural centrality."
            />
            <Metric
              detail={`Lost within ${ghostFinding?.removal_impact?.max_len ?? 4} hops`}
              label="Removal impact"
              value={
                ghostFinding?.removal_impact
                  ? `${ghostFinding.removal_impact.pairs_lost_without_person.toLocaleString()} pairs`
                  : "top-10 only"
              }
              tooltip="Number of person-pairs that lose their bounded shortest path when this person is removed from the communication graph. Measures how much coordination load they carry."
            />
            <Metric
              detail={snapshot.data?.dataset_id ?? "Waiting for snapshot"}
              label="Evidence limits"
              value={`${snapshot.data?.limitations.length ?? "--"} notes`}
              tooltip="Known limitations of the evidence corpus. Absence of a record does not establish that it was deleted — only that it is not in the export."
            />
          </section>

          <details className="query-card" open>
            <summary>How HydraDB answered {activeLens}</summary>
            {activeQuery ? (
              <>
                <pre>{activeQuery.text}</pre>
                <pre className="params">{JSON.stringify(activeQuery.params, null, 2)}</pre>
              </>
            ) : (
              <p className="query-empty">
                No live HydraDB query for this response. Current source: {activeEnvelope?.source ?? "pending"}.
              </p>
            )}
            <footer>
              <span>maxLen: {activeQuery?.max_len ?? "--"}</span>
              <span>round trips: {activeQuery?.round_trips ?? "--"}</span>
              <span>engine: {activeQuery ? `${activeQuery.engine_ms.toFixed(1)}ms` : "--"}</span>
              <span>status: {activeEnvelope?.analysis_status ?? "pending"}</span>
            </footer>
            {activeLens === "org" && comparison ? (
              <p className="comparison-line">
                Client-side equivalent: bounded BFS over {comparison.sampled_people} people in{" "}
                {comparison.client_ms.toFixed(0)} ms — or {comparison.client_equivalent_round_trips.toLocaleString()}{" "}
                per-pair shortest-path calls. HydraDB answers the same sample in {comparison.engine_round_trips || "—"}{" "}
                round trip{comparison.engine_round_trips === 1 ? "" : "s"}.
              </p>
            ) : null}
          </details>

          <section className="evidence-drawer">
            <h3>Evidence + action</h3>
            <p>{evidenceSummary(activeLens, ghostFinding, selectedFaultline, selectedGap)}</p>
            <strong>{recommendedAction(activeLens, ghostFinding, selectedFaultline, selectedGap)}</strong>
            {selectedFaultline?.bridge ? (
              <p className="bridge-suggestion">
                Suggested bridge: {selectedFaultline.bridge.map(suffix).join(" → ")}
              </p>
            ) : null}
            {reportStatus ? <small className="report-status">{reportStatus}</small> : null}
            <EvidenceList evidence={selectedEvidence(activeLens, ghostFinding, selectedFaultline, selectedGap)} />
            <div className="limitations-list">
              <span>Limitations</span>
              {activeEnvelope?.limitations.length ? (
                <ul>
                  {activeEnvelope.limitations.map((limitation) => (
                    <li key={limitation}>{limitation}</li>
                  ))}
                </ul>
              ) : (
                <p>No additional limitations reported.</p>
              )}
            </div>
          </section>
        </aside>
      </div>
    </main>
  );
}

function ImportPanel() {
  const [datasetId, setDatasetId] = useState("imported-snapshot");
  const [directoryFile, setDirectoryFile] = useState<File | null>(null);
  const [identityFile, setIdentityFile] = useState<File | null>(null);
  const [mboxFile, setMboxFile] = useState<File | null>(null);
  const [jiraFile, setJiraFile] = useState<File | null>(null);
  const [gitFile, setGitFile] = useState<File | null>(null);
  const [moduleFile, setModuleFile] = useState<File | null>(null);
  const [channelFile, setChannelFile] = useState<File | null>(null);
  const [messageFile, setMessageFile] = useState<File | null>(null);
  const [slackFiles, setSlackFiles] = useState<File[]>([]);
  const [status, setStatus] = useState<string | null>(null);

  async function readJson(file: File | null, fallback: unknown) {
    if (file === null) return fallback;
    return JSON.parse(await file.text()) as unknown;
  }

  async function importFiles() {
    if (directoryFile === null) {
      setStatus("Choose a directory.json file first");
      return;
    }
    setStatus("Importing exports");
    try {
      const directory = await readJson(directoryFile, []) as Record<string, unknown>[];
      const identity = await readJson(identityFile, {}) as Record<string, string>;
      const modulePrefixes = await readJson(moduleFile, {}) as Record<string, string>;
      const channelModules = await readJson(channelFile, {}) as Record<string, string[]>;
      const messageModules = await readJson(messageFile, {}) as Record<string, string[]>;
      const slackExports: Record<string, Record<string, unknown>[]> = {};
      for (const file of slackFiles) {
        slackExports[file.name.replace(/\.json$/i, "")] = await readJson(file, []) as Record<string, unknown>[];
      }
      const payload: ImportPayload = {
        dataset_id: datasetId.trim() || "imported-snapshot",
        directory,
        identity_map: identity,
        mbox: mboxFile ? [await mboxFile.text()] : [],
        jira_csv: jiraFile ? await jiraFile.text() : undefined,
        git_log: gitFile ? await gitFile.text() : undefined,
        module_prefixes: modulePrefixes,
        slack_exports: slackExports,
        channel_modules: channelModules,
        message_modules: messageModules
      };
      const snapshot = await importSnapshot(payload);
      setStatus(`Imported ${snapshot.node_count} nodes and ${snapshot.edge_count} edges. Reloading…`);
      window.location.reload();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Import failed");
    }
  }

  return (
    <section className="import-panel" aria-label="Load your exports">
      <div>
        <span className="eyeline">Offline ingestion</span>
        <h2>Load your exports</h2>
        <p>Build a local snapshot from directory, mail, JIRA, and git exports.</p>
      </div>
      <div className="import-controls">
        <label>Snapshot ID<input value={datasetId} onChange={(event) => setDatasetId(event.target.value)} /></label>
        <label>Directory JSON<input accept=".json" type="file" onChange={(event) => setDirectoryFile(event.target.files?.[0] ?? null)} /></label>
        <label>Identity map<input accept=".json" type="file" onChange={(event) => setIdentityFile(event.target.files?.[0] ?? null)} /></label>
        <label>mbox<input accept=".mbox,.txt" type="file" onChange={(event) => setMboxFile(event.target.files?.[0] ?? null)} /></label>
        <label>JIRA CSV<input accept=".csv" type="file" onChange={(event) => setJiraFile(event.target.files?.[0] ?? null)} /></label>
        <label>git log<input accept=".log,.txt" type="file" onChange={(event) => setGitFile(event.target.files?.[0] ?? null)} /></label>
        <label>Module prefixes<input accept=".json" type="file" onChange={(event) => setModuleFile(event.target.files?.[0] ?? null)} /></label>
        <label>Slack JSON<input accept=".json" multiple type="file" onChange={(event) => setSlackFiles(Array.from(event.target.files ?? []))} /></label>
        <label>Channel map<input accept=".json" type="file" onChange={(event) => setChannelFile(event.target.files?.[0] ?? null)} /></label>
        <label>Message map<input accept=".json" type="file" onChange={(event) => setMessageFile(event.target.files?.[0] ?? null)} /></label>
        <button className="report-button" onClick={importFiles} type="button">Import snapshot</button>
      </div>
      {status ? <small className="report-status">{status}</small> : null}
    </section>
  );
}

function CytoscapeGraph({
  elements,
  selectedKey,
  onSelect
}: {
  elements: ElementDefinition[];
  selectedKey: string | undefined;
  onSelect: (key: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const hasCanvas = canRenderCanvas();

  useEffect(() => {
    if (!hasCanvas || containerRef.current === null || cyRef.current !== null) {
      return;
    }
    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      layout: { name: "cose", animate: false, padding: 38 },
      style: [
        {
          selector: "node",
          style: {
            "background-color": "#1ecad0",
            "background-gradient-direction": "to-bottom-right",
            "background-gradient-stop-colors": ["#5ee4df", "#158994"],
            "border-color": "#7a8ea1",
            "border-width": 1,
            color: "#c5d3df",
            "font-family": "Inter, system-ui, sans-serif",
            "font-size": 9,
            height: "data(size)",
            label: "data(label)",
            "overlay-opacity": 0,
            "text-margin-y": 8,
            "text-valign": "bottom",
            "text-wrap": "wrap",
            "transition-duration": 260,
            "transition-property": "width height background-color border-color",
            width: "data(size)"
          }
        },
        {
          selector: "node:selected, node.selected",
          style: {
            "border-color": "#1ecad0",
            "border-width": 3,
            color: "#1ecad0"
          }
        },
        {
          selector: "node.excluded",
          style: {
            "background-color": "#3a4652",
            "background-gradient-stop-colors": ["#4a5661", "#2c3640"],
            "border-color": "#f0a95f",
            "border-style": "dashed",
            "border-width": 2,
            color: "#8a97a4",
            opacity: 0.55
          }
        },
        {
          selector: "edge",
          style: {
            "curve-style": "bezier",
            "line-color": "rgba(124, 149, 164, 0.32)",
            opacity: 0.82,
            width: 1.2
          }
        },
        {
          selector: "edge.strong",
          style: { "line-color": "rgba(30, 202, 208, 0.75)", width: 2 }
        },
        {
          selector: "edge.medium",
          style: { "line-color": "rgba(135, 155, 169, 0.48)", width: 1.5 }
        },
        {
          selector: "edge.faultline",
          style: {
            "line-color": "#f05f6b",
            "line-style": "dashed",
            opacity: 1,
            width: 3
          }
        },
        {
          selector: "edge.selected-faultline",
          style: {
            "line-color": "#ff8992",
            "target-arrow-color": "#ff8992",
            opacity: 1,
            width: 5
          }
        }
      ]
    });
    cy.on("tap", "node", (event) => onSelect(String(event.target.id())));
    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [hasCanvas, onSelect]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!hasCanvas || cy === null) {
      return;
    }
    cy.elements().remove();
    cy.add(elements);
    cy.nodes().removeClass("selected");
    if (selectedKey !== undefined) {
      cy.getElementById(selectedKey).addClass("selected");
    }
    cy.layout({ name: "cose", animate: true, animationDuration: 260, padding: 38 }).run();
  }, [elements, hasCanvas, selectedKey]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!hasCanvas || cy === null || globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    let pulsed = false;
    const timer = globalThis.setInterval(() => {
      pulsed = !pulsed;
      cy.edges(".faultline").style({
        opacity: pulsed ? 0.42 : 1,
        width: pulsed ? 5 : 3
      });
    }, 650);
    return () => globalThis.clearInterval(timer);
  }, [elements, hasCanvas]);

  if (!hasCanvas) {
    return (
      <div className="graph-fallback" role="list">
        {elements
          .filter((element) => !("source" in element.data))
          .map((element) => (
            <button
              aria-pressed={element.data.id === selectedKey}
              className={element.data.id === selectedKey ? "fallback-node selected" : "fallback-node"}
              key={String(element.data.id)}
              onClick={() => onSelect(String(element.data.id))}
              type="button"
            >
              {String(element.data.label)}
            </button>
          ))}
      </div>
    );
  }
  return <div className="cy-graph" ref={containerRef} />;
}

function canRenderCanvas() {
  if (typeof document === "undefined") {
    return false;
  }
  if (typeof navigator !== "undefined" && navigator.userAgent.includes("jsdom")) {
    return false;
  }
  try {
    const canvas = document.createElement("canvas");
    return canvas.getContext("2d") !== null;
  } catch {
    return false;
  }
}

function graphElementsFor(
  people: GraphNode[],
  edges: GraphEdge[],
  findings: FaultlineFinding[],
  selectedFaultline: FaultlineFinding | undefined,
  mode: "actual" | "official",
  selectedKey: string | undefined,
  excluded: string[] = [],
  connectedKeys?: Set<string>
): ElementDefinition[] {
  // People with no communication edges (present only in git/tickets) would render as an
  // unlaid-out grid; keep them in the tables but off the canvas.
  const owners = new Set(findings.flatMap((finding) => [finding.source_owner_key, finding.target_owner_key]));
  const visible =
    connectedKeys && connectedKeys.size > 0
      ? people.filter(
          (person) => connectedKeys.has(person.key) || person.key === selectedKey || owners.has(person.key)
        )
      : people;
  const visibleKeys = new Set(visible.map((person) => person.key));
  const nodes = visible.map((person) => ({
    data: {
      id: person.key,
      label: person.name,
      size: mode === "actual" ? person.actual_size : person.official_size
    },
    classes: [person.key === selectedKey ? "selected" : "", excluded.includes(person.key) ? "excluded" : ""]
      .filter(Boolean)
      .join(" ")
  }));
  const communicationEdges = edges
    .filter((edge) => visibleKeys.has(edge.source) && visibleKeys.has(edge.target))
    .map((edge, index) => ({
      data: { id: `edge-${index}`, source: edge.source, target: edge.target },
      classes: edge.strength
    }));
  const faultlineEdges = findings
    .filter(
      (finding) =>
        visibleKeys.has(finding.source_owner_key) &&
        visibleKeys.has(finding.target_owner_key) &&
        finding.source_owner_key !== finding.target_owner_key
    )
    .map((finding, index) => ({
      data: {
        id: `faultline-${index}`,
        source: finding.source_owner_key,
        target: finding.target_owner_key
      },
      classes: finding === selectedFaultline ? "faultline selected-faultline" : "faultline"
    }));
  return [...nodes, ...communicationEdges, ...faultlineEdges];
}

function formatCentrality(finding: GhostFinding | undefined) {
  return finding === undefined ? "--" : finding.sampled_centrality.toFixed(3);
}

function formatRankGap(finding: GhostFinding | undefined) {
  if (finding === undefined) {
    return "--";
  }
  return finding.rank_gap > 0 ? `+${finding.rank_gap} places` : `${finding.rank_gap} places`;
}

function formatHydraStatus(status: "fallback" | "live" | "offline" | undefined) {
  if (status === undefined) {
    return "pending";
  }
  return status;
}

function hydraStatusClass(status: "fallback" | "live" | "offline" | undefined) {
  if (status === "live") {
    return "topbar-metric healthy";
  }
  if (status === "offline") {
    return "topbar-metric unhealthy";
  }
  return "topbar-metric warning";
}

function envelopeForLens(
  lens: Lens,
  ghosts: LensEnvelope<GhostFinding> | undefined,
  faultlines: LensEnvelope<FaultlineFinding> | undefined,
  gaps: LensEnvelope<GapFinding> | undefined
) {
  if (lens === "org") {
    return ghosts;
  }
  if (lens === "faultlines") {
    return faultlines;
  }
  return gaps;
}

function toFaultlineRows(findings: FaultlineFinding[]) {
  return findings.map((finding, index) => ({
    id: `FL-${String(index + 1).padStart(3, "0")}`,
    modules: `${suffix(finding.source_module_key)} → ${suffix(finding.target_module_key)}`,
    owners: `${suffix(finding.source_owner_key)} / ${suffix(finding.target_owner_key)}`,
    "distance (hops)": finding.communication_distance === null ? "none within 4" : String(finding.communication_distance),
    "severity": finding.severity.toFixed(1),
    tier: finding.tier,
    "src conf%": `${finding.source_owner_confidence}`,
    "tgt conf%": `${finding.target_owner_confidence}`
  }));
}

function toGapRows(findings: GapFinding[]) {
  return findings.map((finding, index) => ({
    id: `G-${String(index + 1).padStart(3, "0")}`,
    path:
      finding.reason === "dangling_thread_parent"
        ? `${suffix(finding.successor_keys[0] ?? "artifact:unknown")} → missing ${suffix(finding.phantom_key)}`
        : `${suffix(finding.successor_keys[0] ?? "artifact:unknown")} → ${suffix(finding.phantom_key)} → ${suffix(
            finding.predecessor_keys[0] ?? "artifact:unknown"
          )}`,
    expected: finding.reason === "dangling_thread_parent" ? "thread parent" : finding.expected_kind,
    inferred: finding.inferred_epoch === null ? "unknown" : String(finding.inferred_epoch),
    reason: finding.reason
  }));
}

function evidenceSummary(
  lens: Lens,
  ghost: GhostFinding | undefined,
  faultline: FaultlineFinding | undefined,
  gap: GapFinding | undefined
) {
  if (lens === "org") {
    return ghost
      ? `${ghost.display_name} appears on sampled communication paths; centrality ${ghost.sampled_centrality.toFixed(3)} with degree ${ghost.communication_degree}.`
      : "Select a scored person to inspect Ghost evidence.";
  }
  if (lens === "faultlines") {
    return faultline
      ? `${suffix(faultline.source_module_key)} depends on ${suffix(faultline.target_module_key)}; owners are ${suffix(
          faultline.source_owner_key
        )} and ${suffix(faultline.target_owner_key)}.`
      : "No faultline evidence is currently selected.";
  }
  return gap
    ? `${suffix(gap.phantom_key)} is a structurally missing ${gap.expected_kind}; absence does not establish deletion.`
    : "No gap evidence is currently selected.";
}

function recommendedAction(
  lens: Lens,
  ghost: GhostFinding | undefined,
  faultline: FaultlineFinding | undefined,
  gap: GapFinding | undefined
) {
  if (lens === "org") {
    return ghost
      ? `Action: document ${ghost.display_name}'s handoff paths and add a backup owner.`
      : "Action: select a person with a Ghost score.";
  }
  if (lens === "faultlines") {
    return faultline
      ? `Action: introduce ${suffix(faultline.source_owner_key)} ↔ ${suffix(faultline.target_owner_key)} for this dependency.`
      : "Action: no introduction needed.";
  }
  return gap
    ? `Action: request the missing ${gap.expected_kind} record or mark the source export incomplete.`
    : "Action: no missing step selected.";
}

function selectedEvidence(
  lens: Lens,
  ghost: GhostFinding | undefined,
  faultline: FaultlineFinding | undefined,
  gap: GapFinding | undefined
) {
  if (lens === "org") {
    return ghost?.evidence ?? [];
  }
  if (lens === "faultlines") {
    return faultline?.evidence ?? [];
  }
  return gap?.evidence ?? [];
}

function EvidenceList({ evidence }: { evidence: EvidenceSummary[] }) {
  if (evidence.length === 0) {
    return <p className="evidence-empty">No source evidence is attached to this finding.</p>;
  }
  return (
    <div className="evidence-list">
      {evidence.map((record) => (
        <article className="evidence-record" key={record.evidence_id}>
          <div>
            <span>{record.source_type}</span>
            <strong>{record.predicate}</strong>
          </div>
          <p>{record.redacted_excerpt || "No redacted excerpt available."}</p>
          <dl>
            <div>
              <dt>record</dt>
              <dd>{record.source_record_id}</dd>
            </div>
            <div>
              <dt>confidence</dt>
              <dd>{record.confidence}%</dd>
            </div>
            <div>
              <dt>class</dt>
              <dd>{record.evidence_class}</dd>
            </div>
            <div>
              <dt>sha</dt>
              <dd title={record.content_sha256}>{shortSha(record.content_sha256)}</dd>
            </div>
          </dl>
          <code>{record.evidence_id}</code>
        </article>
      ))}
    </div>
  );
}

function shortSha(value: string) {
  return value.length > 12 ? `${value.slice(0, 12)}…` : value;
}

function suffix(value: string) {
  return value.split(":").at(-1) ?? value;
}

function Icon({ path }: { path: string }) {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d={path} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

function Metric({ label, value, detail, tooltip }: { label: string; value: string; detail: string; tooltip?: string }) {
  return (
    <div className="metric" title={tooltip}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function GraphLegend({ hiddenIsolates = 0 }: { hiddenIsolates?: number }) {
  return (
    <div className="graph-legend" aria-label="Graph legend">
      {hiddenIsolates > 0 ? (
        <span className="legend-note">{hiddenIsolates} people without reply edges hidden</span>
      ) : null}
      <span>
        <i className="legend-dot communication" /> communication
      </span>
      <span>
        <i className="legend-dot faultline" /> faultline
      </span>
      <span>
        <i className="legend-dot phantom" /> phantom
      </span>
    </div>
  );
}

function DataTable({
  emptyText,
  onRowSelect,
  selectedIndex,
  title,
  rows
}: {
  emptyText: string;
  onRowSelect?: (index: number) => void;
  selectedIndex?: number;
  title: string;
  rows: Array<Record<string, string>>;
}) {
  const keys = Object.keys(rows[0] ?? {});

  return (
    <section className="table-panel">
      <h3>{title}</h3>
      {rows.length === 0 ? (
        <p className="table-empty">{emptyText}</p>
      ) : (
        <table>
          <thead>
            <tr>
              {keys.map((key) => (
                <th key={key}>{key}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr
                className={rowIndex === selectedIndex ? "data-row selected" : "data-row"}
                key={row.id}
                onClick={() => onRowSelect?.(rowIndex)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onRowSelect?.(rowIndex);
                  }
                }}
                tabIndex={onRowSelect === undefined ? undefined : 0}
              >
                {keys.map((key) => (
                  <td data-label={key} key={key}>
                    {row[key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function GapTimeline({
  emptyText,
  findings,
  onSelect,
  selectedIndex,
  chainPending
}: {
  emptyText: string;
  findings: GapFinding[];
  onSelect: (index: number) => void;
  selectedIndex: number;
  chainPending: boolean;
}) {
  const selected = findings[selectedIndex];
  return (
    <section className="table-panel gap-timeline">
      <div className="panel-heading">
        <h3>Gaps</h3>
        <span className="gap-caveat">Absence in the corpus is not proof of deletion.</span>
      </div>
      {selected ? (
        <div className="chain" aria-label="Chain of custody">
          {selected.chain ? (
            <ol className="chain-track">
              {selected.chain.node_keys.map((key, index) => (
                <li
                  className={selected.chain?.phantom_indices.includes(index) ? "chain-hop phantom" : "chain-hop"}
                  key={`${key}-${index}`}
                  title={selected.chain?.phantom_indices.includes(index)
                    ? "Phantom node: structurally required by the graph but absent from the evidence corpus. Absence does not establish deletion."
                    : undefined}
                >
                  <span className="chain-dot" />
                  <code>{suffix(key)}</code>
                  {selected.chain?.phantom_indices.includes(index) ? <small>missing · {selected.reason}</small> : null}
                </li>
              ))}
            </ol>
          ) : (
            <p className="chain-empty">
              {chainPending
                ? "Tracing the chain with algo.SPpaths…"
                : selected.reason === "dangling_thread_parent"
                  ? `${suffix(selected.successor_keys[0] ?? "")} replies to a parent that is not in the corpus.`
                  : "No live chain for this record."}
            </p>
          )}
        </div>
      ) : null}
      {findings.length === 0 ? (
        <p className="table-empty">{emptyText}</p>
      ) : (
        <div className="timeline-list">
          {findings.map((finding, index) => (
            <button
              className={index === selectedIndex ? "timeline-row selected" : "timeline-row"}
              key={finding.phantom_key}
              onClick={() => onSelect(index)}
              type="button"
            >
              <span>{`G-${String(index + 1).padStart(3, "0")}`}</span>
              <ol>
                <li>{suffix(finding.successor_keys[0] ?? "artifact:unknown")}</li>
                <li className="phantom">{shortKey(finding.phantom_key)}</li>
                <li>{suffix(finding.predecessor_keys[0] ?? "artifact:unknown")}</li>
              </ol>
              <small>
                {finding.expected_kind} · {finding.reason.replaceAll("_", " ")}
              </small>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function requestForGap(finding: GapFinding): GapPathRequest | undefined {
  const source = finding.successor_keys[0];
  const target = finding.predecessor_keys[0];
  if (source === undefined || target === undefined) {
    return undefined;
  }
  return { source_artifact_key: source, target_artifact_key: target };
}

function shortKey(value: string) {
  const last = suffix(value);
  return last.length > 28 ? `${last.slice(0, 26)}…` : last;
}

function nameFor(people: GraphNode[], key: string) {
  return people.find((person) => person.key === key)?.name ?? suffix(key);
}

function formatSignedRankGap(gap: number) {
  return gap > 0 ? `+${gap}` : String(gap);
}

function Notice({ text, tone }: { text: string; tone: "bad" | "warn" }) {
  return <div className={`notice ${tone}`}>{text}</div>;
}
