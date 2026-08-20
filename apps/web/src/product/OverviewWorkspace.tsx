import type { HealthResponse, SnapshotResponse } from "../api";
import type { ProductView, RiskItem } from "./types";
import { riskKindLabel } from "./riskModel";

export function OverviewWorkspace({
  risks,
  health,
  snapshot,
  totalRiskCount,
  onView,
  onRisk
}: {
  risks: RiskItem[];
  health?: HealthResponse;
  snapshot?: SnapshotResponse;
  totalRiskCount?: number;
  onView: (view: ProductView) => void;
  onRisk: (id: string) => void;
}) {
  const p1 = risks.filter((risk) => risk.priority === "P1").length;
  const engine =
    health?.hydra.status === "live" && health.hydra.graph_loaded
      ? "HydraDB live"
      : health?.hydra.status === "live" || health?.hydra.status === "fallback"
        ? "Snapshot analytics"
        : "Offline";

  return (
    <section className="overview-workspace">
      <header className="overview-hero">
        <div>
          <h1>Overview</h1>
          <p>
            Status for the active evidence snapshot, then the highest-priority coordination risks.
          </p>
        </div>
        <button onClick={() => onView("risks")} type="button">
          Open risks
        </button>
      </header>

      <p className="overview-status-line" role="status">
        <span>{engine}</span>
        <span aria-hidden="true">·</span>
        <span>{snapshot?.dataset_id ?? "Loading dataset"}</span>
        <span aria-hidden="true">·</span>
        <span>
          {typeof totalRiskCount === "number"
            ? `${totalRiskCount} signals in corpus`
            : `${risks.length} signals`}
        </span>
        {snapshot?.limitations.length ? (
          <>
            <span aria-hidden="true">·</span>
            <span>{snapshot.limitations.length} limitations</span>
          </>
        ) : null}
      </p>

      <div className="overview-grid">
        <div className="overview-panel">
          <div className="panel-heading">
            <div>
              <h2>Top risks</h2>
              <p>
                {p1 ? `${p1} priority-1 in view` : "Sorted by priority and confidence"}
              </p>
            </div>
            <button onClick={() => onView("risks")} type="button">
              View all
            </button>
          </div>
          <div className="top-risk-list">
            {risks.slice(0, 5).map((risk) => (
              <button key={risk.id} onClick={() => onRisk(risk.id)} type="button">
                <span className={`priority priority-${risk.priority.toLowerCase()}`}>
                  {risk.priority}
                </span>
                <span>
                  <strong>{risk.title}</strong>
                  <small>
                    {riskKindLabel(risk.kind)} · {risk.confidence}%
                  </small>
                </span>
                <b>{">"}</b>
              </button>
            ))}
            {!risks.length ? (
              <p className="overview-empty">No high-signal risks in the current filter set.</p>
            ) : null}
          </div>
        </div>

        <aside className="overview-panel runtime-panel">
          <div className="panel-heading">
            <div>
              <h2>Runtime</h2>
              <p>What this session is serving</p>
            </div>
          </div>
          <dl>
            <div>
              <dt>Analytics engine</dt>
              <dd className={health?.hydra.status === "live" && health.hydra.graph_loaded ? "good" : "warn"}>{engine}</dd>
            </div>
            <div>
              <dt>Dataset</dt>
              <dd>{snapshot?.dataset_id ?? "Loading"}</dd>
            </div>
            <div>
              <dt>Graph size</dt>
              <dd>
                {snapshot
                  ? `${snapshot.node_count} nodes · ${snapshot.edge_count} edges`
                  : "—"}
              </dd>
            </div>
            <div>
              <dt>Coverage</dt>
              <dd className={snapshot?.limitations.length ? "warn" : "good"}>
                {snapshot?.limitations.length
                  ? `${snapshot.limitations.length} noted limits`
                  : "Complete"}
              </dd>
            </div>
          </dl>
          {snapshot?.limitations[0] ? (
            <p className="runtime-limitation">{snapshot.limitations[0]}</p>
          ) : null}
        </aside>
      </div>
    </section>
  );
}
