import cytoscape from "cytoscape";
import type { Core, ElementDefinition } from "cytoscape";
import { useEffect, useMemo, useRef, useState } from "react";
import { DEFAULT_GAP_REQUEST } from "./api";
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
  const [gapRequest, setGapRequest] = useState<GapPathRequest>(DEFAULT_GAP_REQUEST);
  const { faultlines, gapPath, ghosts, graph, health, snapshot } = useXraySnapshot(gapRequest);
  const people = graph.data?.nodes ?? [];
  const defaultSelectedKey = people.find((person) => person.selected)?.key ?? people[0]?.key;
  const selectedKey = people.some((person) => person.key === selectedNodeKey) ? selectedNodeKey : defaultSelectedKey;
  const selected = people.find((person) => person.key === selectedKey);
  const ghostFinding = ghosts.data?.findings.find((finding) => finding.person_key === selected?.key);
  const faultlineFindings = faultlines.data?.findings ?? [];
  const gapFindings = gapPath.data?.findings ?? [];
  const selectedFaultline = faultlineFindings[selectedFaultlineIndex] ?? faultlineFindings[0];
  const selectedGap = gapFindings[selectedGapIndex] ?? gapFindings[0];
  const activeEnvelope = envelopeForLens(activeLens, ghosts.data, faultlines.data, gapPath.data);
  const activeQuery = activeEnvelope?.executed_query;
  const queryErrors = [
    ["health", health.isError],
    ["snapshot", snapshot.isError],
    ["graph", graph.isError],
    ["ghost", ghosts.isError],
    ["faultlines", faultlines.isError],
    ["gaps", gapPath.isError]
  ].filter(([, failed]) => failed);
  const hasError = queryErrors.length > 0;
  const isLoading =
    health.isPending ||
    snapshot.isPending ||
    graph.isPending ||
    ghosts.isPending ||
    faultlines.isPending ||
    gapPath.isPending;
  const graphElements = useMemo(
    () => graphElementsFor(people, graph.data?.edges ?? [], faultlineFindings, selectedFaultline, mode, selectedKey),
    [faultlineFindings, graph.data?.edges, mode, people, selectedFaultline, selectedKey]
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
            <label>
              Centrality
              <select
                aria-label="Centrality mode"
                onChange={(event) => setMode(event.target.value as "actual" | "official")}
                value={mode}
              >
                <option value="actual">Actual normalized</option>
                <option value="official">Official rank</option>
              </select>
            </label>
            <div className="scale">Official → Actual sizes animate on the graph</div>
            <div className="query-source">
              {activeEnvelope?.source ?? "fixture"} · {activeEnvelope?.analysis_status ?? "pending"}
            </div>
          </div>

          <div className="graph-stage" data-lens={activeLens}>
            {graph.isError ? <Notice text="Graph query failed. Other lens data can still render." tone="bad" /> : null}
            <CytoscapeGraph elements={graphElements} onSelect={setSelectedNodeKey} selectedKey={selectedKey} />
            <GraphLegend />
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
              emptyText={gapPath.isPending ? "Loading gaps" : "No API gaps"}
              findings={gapFindings}
              onRequestChange={setGapRequest}
              onSelect={setSelectedGapIndex}
              request={gapRequest}
              selectedIndex={selectedGapIndex}
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
            />
            <Metric
              detail={`Formal rank: ${ghostFinding?.formal_rank ?? "--"}`}
              label="Rank gap"
              value={formatRankGap(ghostFinding)}
            />
            <Metric
              detail={`Lost within ${ghostFinding?.removal_impact.max_len ?? 4} hops`}
              label="Removal impact"
              value={`${ghostFinding?.removal_impact.pairs_lost_without_person ?? "--"} pairs`}
            />
            <Metric
              detail={snapshot.data?.dataset_id ?? "Waiting for snapshot"}
              label="Evidence limits"
              value={`${snapshot.data?.limitations.length ?? "--"} notes`}
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
          </details>

          <section className="evidence-drawer">
            <h3>Evidence + action</h3>
            <p>{evidenceSummary(activeLens, ghostFinding, selectedFaultline, selectedGap)}</p>
            <strong>{recommendedAction(activeLens, ghostFinding, selectedFaultline, selectedGap)}</strong>
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
  selectedKey: string | undefined
): ElementDefinition[] {
  const nodes = people.map((person) => ({
    data: {
      id: person.key,
      label: person.name,
      size: mode === "actual" ? person.actual_size : person.official_size
    },
    classes: person.key === selectedKey ? "selected" : ""
  }));
  const communicationEdges = edges.map((edge, index) => ({
    data: { id: `edge-${index}`, source: edge.source, target: edge.target },
    classes: edge.strength
  }));
  const faultlineEdges = findings.map((finding, index) => ({
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
    distance: finding.communication_distance === null ? "none within 4" : String(finding.communication_distance),
    severity: finding.severity.toFixed(1),
    tier: finding.tier
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

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function GraphLegend() {
  return (
    <div className="graph-legend" aria-label="Graph legend">
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
  onRequestChange,
  onSelect,
  request,
  selectedIndex
}: {
  emptyText: string;
  findings: GapFinding[];
  onRequestChange: (request: GapPathRequest) => void;
  onSelect: (index: number) => void;
  request: GapPathRequest;
  selectedIndex: number;
}) {
  const artifactOptions = artifactOptionsFrom(findings, request);

  return (
    <section className="table-panel gap-timeline">
      <div className="panel-heading">
        <h3>Gaps</h3>
        <span>
          {request.source_artifact_key} to {request.target_artifact_key}
        </span>
      </div>
      <div className="gap-controls" aria-label="Gap path controls">
        <label>
          Source artifact
          <select
            aria-label="Source artifact"
            onChange={(event) => onRequestChange({ ...request, source_artifact_key: event.target.value })}
            value={request.source_artifact_key}
          >
            {artifactOptions.map((artifact) => (
              <option key={`source-${artifact}`} value={artifact}>
                {suffix(artifact)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Target artifact
          <select
            aria-label="Target artifact"
            onChange={(event) => onRequestChange({ ...request, target_artifact_key: event.target.value })}
            value={request.target_artifact_key}
          >
            {artifactOptions.map((artifact) => (
              <option key={`target-${artifact}`} value={artifact}>
                {suffix(artifact)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {findings.length === 0 ? (
        <p className="table-empty">{emptyText}</p>
      ) : (
        findings.map((finding, index) => (
          <button
            className={index === selectedIndex ? "timeline-row selected" : "timeline-row"}
            key={finding.phantom_key}
            onClick={() => onSelect(index)}
            type="button"
          >
            <span>{`G-${String(index + 1).padStart(3, "0")}`}</span>
            <ol>
              <li>{suffix(finding.successor_keys[0] ?? "artifact:unknown")}</li>
              <li className="phantom">{suffix(finding.phantom_key)}</li>
              <li>{suffix(finding.predecessor_keys[0] ?? "artifact:unknown")}</li>
            </ol>
            <small>
              {finding.expected_kind} · {finding.reason}
            </small>
          </button>
        ))
      )}
    </section>
  );
}

function artifactOptionsFrom(findings: GapFinding[], request: GapPathRequest) {
  const artifacts = new Set([request.source_artifact_key, request.target_artifact_key]);
  findings.forEach((finding) => {
    finding.predecessor_keys.forEach((key) => artifacts.add(key));
    finding.successor_keys.forEach((key) => artifacts.add(key));
  });
  return Array.from(artifacts).sort();
}

function Notice({ text, tone }: { text: string; tone: "bad" | "warn" }) {
  return <div className={`notice ${tone}`}>{text}</div>;
}
