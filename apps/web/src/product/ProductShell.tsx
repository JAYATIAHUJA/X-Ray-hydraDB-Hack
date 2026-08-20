import type { ReactNode } from "react";
import type { HealthResponse, SnapshotResponse } from "../api";
import { XRayLogo } from "../Brand";
import type { ProductView } from "./types";
import { Icon, type IconName } from "./Icons";

const NAV: Array<{ id: ProductView; label: string; icon: IconName }> = [
  { id: "overview", label: "Overview", icon: "overview" },
  { id: "risks", label: "Risks", icon: "risk" },
  { id: "ask", label: "Ask X-Ray", icon: "ask" },
  { id: "graph", label: "Explore graph", icon: "graph" }
];

export function ProductShell({
  children,
  view,
  onView,
  health,
  healthState = "ready",
  snapshot
}: {
  children: ReactNode;
  view: ProductView;
  onView: (view: ProductView) => void;
  health?: HealthResponse;
  healthState?: "loading" | "error" | "ready";
  snapshot?: SnapshotResponse;
}) {
  const rawEngine =
    healthState === "loading"
      ? "connecting"
      : healthState === "error"
        ? "offline"
        : (health?.hydra.status ?? "offline");
  // Reachable Hydra with no loaded dataset graph is still snapshot analytics.
  const engineStatus =
    rawEngine === "live" && health?.hydra.graph_loaded === false ? "fallback" : rawEngine;
  const engineLabel =
    engineStatus === "live"
      ? "HydraDB live"
      : engineStatus === "fallback"
        ? "Snapshot analytics"
        : engineStatus === "connecting"
          ? "Connecting…"
          : "Offline";
  const dataset = snapshot?.dataset_id ?? "Loading…";

  return (
    <div className="product-shell">
      <aside className="product-sidebar">
        <a className="product-brand" href="/">
          <XRayLogo />
          <span>X-Ray</span>
        </a>
        <nav aria-label="Product navigation">
          {NAV.map((item) => (
            <button
              aria-current={view === item.id ? "page" : undefined}
              key={item.id}
              onClick={() => onView(item.id)}
              type="button"
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span>{engineLabel}</span>
          <small>{dataset}</small>
        </div>
      </aside>
      <div className="product-main">
        <header className="product-topbar">
          <div className="workspace-switcher">
            <span>Workspace</span>
            <strong>{dataset}</strong>
          </div>
          <p className="runtime-quiet" role="status">
            <i
              className={`state-dot state-${
                engineStatus === "connecting"
                  ? "partial"
                  : engineStatus === "fallback"
                    ? "fallback"
                    : engineStatus
              }`}
            />
            {engineLabel}
            {snapshot?.dataset_id ? ` · ${snapshot.dataset_id}` : ""}
          </p>
        </header>
        {children}
      </div>
    </div>
  );
}
