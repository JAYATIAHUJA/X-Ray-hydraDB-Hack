import type { ReactNode } from "react";
import type { HealthResponse, SnapshotResponse } from "../api";
import { XRayLogo } from "../Brand";
import type { ProductView } from "./types";
import { Icon, type IconName } from "./Icons";

const NAV: Array<{ id: ProductView; label: string; icon: IconName }> = [
  { id: "overview", label: "Overview", icon: "overview" },
  { id: "risks", label: "Risks", icon: "risk" },
  { id: "ask", label: "Ask X-Ray", icon: "ask" },
  { id: "identities", label: "Identity review", icon: "identity" },
  { id: "repairs", label: "Repairs", icon: "repair" },
  { id: "graph", label: "Explore graph", icon: "graph" },
  { id: "imports", label: "Imports", icon: "import" },
  { id: "actions", label: "Actions", icon: "action" },
  { id: "settings", label: "Settings", icon: "settings" }
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
  const engineStatus =
    healthState === "loading"
      ? "connecting"
      : healthState === "error"
        ? "offline"
        : (health?.hydra.status ?? "offline");
  const engineLabel =
    engineStatus === "live"
      ? "HydraDB live"
      : engineStatus === "fallback"
        ? "Snapshot analytics"
        : engineStatus === "connecting"
          ? "Connecting…"
          : "Offline";
  const dataPartial = (snapshot?.limitations.length ?? 0) > 0;

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
          <span>Evidence platform</span>
          <small>{snapshot?.dataset_id ?? "Loading workspace"}</small>
        </div>
      </aside>
      <div className="product-main">
        <header className="product-topbar">
          <div className="workspace-switcher">
            <span>Workspace</span>
            <strong>{snapshot?.dataset_id ?? "Loading..."}</strong>
          </div>
          <div className="runtime-state">
            <div>
              <span>Engine status</span>
              <strong>
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
              </strong>
            </div>
            <div>
              <span>Data status</span>
              <strong>
                <i className={`state-dot ${dataPartial ? "state-partial" : "state-live"}`} />
                {dataPartial ? "Partial coverage" : "Ready"}
              </strong>
            </div>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}
