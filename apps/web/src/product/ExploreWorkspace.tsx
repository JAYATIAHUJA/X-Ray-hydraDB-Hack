import { useMemo, useState } from "react";
import type { GraphResponse } from "../api";
import { Graph3D, GRAPH_MAX_NODES, type Graph3DEdge, type Graph3DNode } from "../Graph3D";
import type { RiskItem } from "./types";
import { Icon } from "./Icons";

export function ExploreWorkspace({
  graph,
  risks,
  loading = false,
  error
}: {
  graph?: GraphResponse;
  risks: RiskItem[];
  loading?: boolean;
  error?: string;
}) {
  const [mode, setMode] = useState<"visual" | "list">("visual");
  const [sizeMode, setSizeMode] = useState<"official" | "actual">("actual");
  const [search, setSearch] = useState("");
  const [selectedKey, setSelectedKey] = useState<string>();
  const riskByKey = useMemo(() => {
    const map = new Map<string, RiskItem>();
    for (const risk of risks) {
      if (risk.sourceKey) map.set(risk.sourceKey, risk);
      if (risk.targetKey) map.set(risk.targetKey, risk);
    }
    return map;
  }, [risks]);

  const totalNodes = graph?.nodes.length ?? 0;
  const visible = (graph?.nodes ?? []).filter((node) =>
    `${node.name} ${node.title} ${node.team}`.toLowerCase().includes(search.trim().toLowerCase())
  );
  const renderedCount = Math.min(visible.length, GRAPH_MAX_NODES);
  const visibleKeys = new Set(visible.map((node) => node.key));
  const nodes: Graph3DNode[] = visible.map((node) => {
    const risk = riskByKey.get(node.key);
    const sized = sizeMode === "official" ? node.official_size : node.actual_size;
    return {
      key: node.key,
      label: node.name,
      size: Math.max(20, sized),
      focus: Boolean(risk) || node.selected,
      role:
        risk?.kind === "key-person"
          ? "ghost"
          : risk?.kind === "coordination"
            ? "faultline"
            : risk?.kind === "missing-evidence"
              ? "gap"
              : "none"
    };
  });
  const edges: Graph3DEdge[] = (graph?.edges ?? [])
    .filter((edge) => visibleKeys.has(edge.source) && visibleKeys.has(edge.target))
    .map((edge) => ({ ...edge, kind: edge.strength }));
  const selected = graph?.nodes.find((node) => node.key === selectedKey);

  return (
    <section className="explore-workspace">
      <header className="section-heading">
        <div>
          <h1>Explore graph</h1>
          <p>
            Toggle Official vs Actual size — formal rank vs observed coordination load (Ghost money
            shot).
          </p>
        </div>
        <div className="graph-stats">
          <span>
            <b>{totalNodes}</b> people
          </span>
          <span>
            <b>{graph?.edges.length ?? 0}</b> links
          </span>
          {visible.length > GRAPH_MAX_NODES ? (
            <span className="graph-truncate">
              Showing {renderedCount} of {visible.length}
            </span>
          ) : null}
        </div>
      </header>
      <div className="graph-toolbar">
        <label>
          <Icon name="search" />
          <span className="sr-only">Search people or teams</span>
          <input
            placeholder="Search people or teams..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <div role="group" aria-label="Node size mode" className="segmented size-mode">
          <button
            aria-pressed={sizeMode === "official"}
            onClick={() => setSizeMode("official")}
            type="button"
          >
            Official
          </button>
          <button
            aria-pressed={sizeMode === "actual"}
            onClick={() => setSizeMode("actual")}
            type="button"
          >
            Actual
          </button>
        </div>
        <div role="group" aria-label="Graph view">
          <button aria-pressed={mode === "visual"} onClick={() => setMode("visual")} type="button">
            Visual
          </button>
          <button aria-pressed={mode === "list"} onClick={() => setMode("list")} type="button">
            Accessible list
          </button>
        </div>
      </div>
      {error ? (
        <div className="workspace-error" role="alert">
          {error}
        </div>
      ) : null}
      {loading && !graph ? (
        <div className="graph-empty" role="status">
          <Icon name="graph" />
          <h2>Loading graph…</h2>
          <p>Waiting for the active snapshot.</p>
        </div>
      ) : (
        <div className={`graph-content ${selected ? "has-selection" : ""}`}>
          <div className="graph-stage">
            {visible.length === 0 ? (
              <div className="graph-empty">
                <Icon name="graph" />
                <h2>{error ? "Graph unavailable" : "No people match this search"}</h2>
                <p>
                  {error
                    ? "Retry after the API is reachable."
                    : "Clear the search to restore the complete snapshot."}
                </p>
              </div>
            ) : mode === "visual" ? (
              <>
                <Graph3D
                  edges={edges}
                  initialZoom={1.45}
                  nodes={nodes}
                  onSelect={setSelectedKey}
                  selectedKey={selectedKey}
                />
                <div className="graph-legend">
                  <span>
                    <i className="legend-ghost" />
                    Key person
                  </span>
                  <span>
                    <i className="legend-faultline" />
                    Faultline
                  </span>
                  <span>
                    <i className="legend-neutral" />
                    Context
                  </span>
                </div>
              </>
            ) : (
              <table className="graph-list">
                <thead>
                  <tr>
                    <th>Person</th>
                    <th>Title</th>
                    <th>Team</th>
                    <th>Observed</th>
                    <th>Finding</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((node) => {
                    const risk = riskByKey.get(node.key);
                    return (
                      <tr key={node.key}>
                        <td>
                          <button onClick={() => setSelectedKey(node.key)} type="button">
                            {node.name}
                          </button>
                        </td>
                        <td>{node.title}</td>
                        <td>{node.team}</td>
                        <td>{node.actual_size}</td>
                        <td>{risk?.title ?? "Context only"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
          {selected ? (
            <aside className="node-detail">
              <button
                aria-label="Close person detail"
                onClick={() => setSelectedKey(undefined)}
                type="button"
              >
                <Icon name="close" />
              </button>
              <span className="eyebrow">Selected node</span>
              <h2>{selected.name}</h2>
              <p>{selected.title}</p>
              <dl>
                <div>
                  <dt>Team</dt>
                  <dd>{selected.team}</dd>
                </div>
                <div>
                  <dt>{sizeMode === "official" ? "Formal size (Official)" : "Observed size (Actual)"}</dt>
                  <dd>{sizeMode === "official" ? selected.official_size : selected.actual_size}</dd>
                </div>
                <div>
                  <dt>{sizeMode === "official" ? "Observed (Actual)" : "Formal (Official)"}</dt>
                  <dd>{sizeMode === "official" ? selected.actual_size : selected.official_size}</dd>
                </div>
              </dl>
              {riskByKey.get(selected.key) ? (
                <div className="node-risk">
                  <strong>Related finding</strong>
                  <p>{riskByKey.get(selected.key)?.title}</p>
                </div>
              ) : (
                <p className="node-note">
                  This node provides relationship context and has no prioritized finding.
                </p>
              )}
            </aside>
          ) : null}
        </div>
      )}
    </section>
  );
}
