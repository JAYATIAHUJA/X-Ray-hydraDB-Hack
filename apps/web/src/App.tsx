import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";
import type { FaultlineFinding, GapFinding, GhostFinding } from "./api";
import type { Lens } from "./data";
import { queryText } from "./data";
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
  const { faultlines, gapPath, ghosts, graph, snapshot } = useXraySnapshot();
  const people = graph.data?.nodes ?? [];
  const defaultSelectedKey = people.find((person) => person.selected)?.key ?? people[0]?.key;
  const selectedKey = people.some((person) => person.key === selectedNodeKey) ? selectedNodeKey : defaultSelectedKey;
  const selected = people.find((person) => person.key === selectedKey);
  const ghostFinding =
    ghosts.data?.findings.find((finding) => finding.person_key === selected?.key) ??
    ghosts.data?.findings[0];
  const faultlineRows = toFaultlineRows(faultlines.data?.findings ?? []);
  const gapRows = toGapRows(gapPath.data?.findings ?? []);
  const hasError = snapshot.isError || graph.isError || ghosts.isError || faultlines.isError || gapPath.isError;
  const isLoading =
    snapshot.isPending || graph.isPending || ghosts.isPending || faultlines.isPending || gapPath.isPending;
  const graphLinks = useMemo(
    () =>
      (graph.data?.edges ?? []).map((link) => ({
        ...link,
        source: people.find((person) => person.key === link.source),
        target: people.find((person) => person.key === link.target)
      })),
    [graph.data?.edges, people]
  );

  useEffect(() => {
    if (selectedNodeKey === undefined && defaultSelectedKey !== undefined) {
      setSelectedNodeKey(defaultSelectedKey);
    }
  }, [defaultSelectedKey, selectedNodeKey]);

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
        <div className="status-pill">Local fixture</div>
        <div className={hasError ? "topbar-metric unhealthy" : "topbar-metric healthy"}>
          {hasError ? "API offline" : isLoading ? "Loading" : "Healthy"}
        </div>
        <div className="topbar-metric">
          Graph: {snapshot.data?.node_count ?? "--"} nodes / {snapshot.data?.edge_count ?? "--"} edges
        </div>
        <div className="topbar-metric">HydraDB: {ghosts.data?.analysis_status ?? "pending"}</div>
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
            <span>Data</span>
            <strong>Local</strong>
          </div>
        </aside>

        <section className="canvas-panel" aria-label={`${activeLens} workspace`}>
          <div className="toolbar">
            <label>
              Centrality
              <select
                aria-label="Centrality mode"
                value={mode}
                onChange={(event) => setMode(event.target.value as "actual" | "official")}
              >
                <option value="actual">Actual normalized</option>
                <option value="official">Official rank</option>
              </select>
            </label>
            <div className="scale">
              Low <span /> <span /> <span /> <span /> High
            </div>
            <label className="check">
              <input defaultChecked type="checkbox" /> Log scale node sizes
            </label>
            <input aria-label="Search nodes" placeholder="Search nodes (Ctrl+K)" />
          </div>

          <div className="graph-stage">
            <svg aria-hidden="true" className="graph-lines" viewBox="0 0 100 100" preserveAspectRatio="none">
              {graphLinks.map((link) =>
                link.source && link.target ? (
                  <line
                    className={`edge ${link.strength}`}
                    key={`${link.source.key}-${link.target.key}`}
                    x1={link.source.x}
                    x2={link.target.x}
                    y1={link.source.y}
                    y2={link.target.y}
                  />
                ) : null
              )}
            </svg>
            {people.map((person) => {
              const size = mode === "actual" ? person.actual_size : person.official_size;
              return (
                <button
                  aria-pressed={person.key === selectedKey}
                  className={person.key === selectedKey ? "person-node selected" : "person-node"}
                  key={person.key}
                  onClick={() => setSelectedNodeKey(person.key)}
                  style={
                    {
                      "--node-size": `${size}px`,
                      left: `${person.x}%`,
                      top: `${person.y}%`
                    } as CSSProperties
                  }
                  type="button"
                >
                  <span>{person.name}</span>
                  <small>{person.title}</small>
                </button>
              );
            })}
          </div>

          <div className="bottom-grid">
            <DataTable
              emptyText={faultlines.isPending ? "Loading faultlines" : "No API faultlines"}
              rows={faultlineRows}
              title="Faultlines"
            />
            <DataTable
              emptyText={gapPath.isPending ? "Loading gaps" : "No API gaps"}
              rows={gapRows}
              title="Gaps"
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
            <summary>How HydraDB Answered This</summary>
            <pre>{queryText}</pre>
            <footer>
              <span>maxLen: 4</span>
              <span>resultLimit: 100</span>
              <span>status: {ghosts.data?.analysis_status ?? "pending"}</span>
            </footer>
          </details>
        </aside>
      </div>
    </main>
  );
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

function toFaultlineRows(findings: FaultlineFinding[]) {
  return findings.map((finding, index) => ({
    id: `FL-${String(index + 1).padStart(3, "0")}`,
    modules: `${suffix(finding.source_module_key)} -> ${suffix(finding.target_module_key)}`,
    owners: `${suffix(finding.source_owner_key)} / ${suffix(finding.target_owner_key)}`,
    distance: finding.communication_distance === null ? "none within 4" : String(finding.communication_distance),
    severity: finding.severity.toFixed(1),
    tier: finding.tier
  }));
}

function toGapRows(findings: GapFinding[]) {
  return findings.map((finding, index) => ({
    id: `G-${String(index + 1).padStart(3, "0")}`,
    path: `${suffix(finding.successor_keys[0] ?? "artifact:unknown")} -> ${suffix(finding.phantom_key)} -> ${suffix(
      finding.predecessor_keys[0] ?? "artifact:unknown"
    )}`,
    expected: finding.expected_kind,
    inferred: finding.inferred_epoch === null ? "unknown" : String(finding.inferred_epoch),
    reason: finding.reason
  }));
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

function DataTable({
  emptyText,
  title,
  rows
}: {
  emptyText: string;
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
            <tr>{keys.map((key) => <th key={key}>{key}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
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
