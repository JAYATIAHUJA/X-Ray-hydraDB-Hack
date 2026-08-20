import { useMemo, useState } from "react";
import { useXraySnapshot } from "./queries";
import { buildRiskInbox } from "./product/riskModel";
import { ProductShell } from "./product/ProductShell";
import { RiskDetail } from "./product/RiskDetail";
import { EMPTY_ACTION, useRiskActions } from "./product/useRiskActions";
import { ExploreWorkspace } from "./product/ExploreWorkspace";
import { OverviewWorkspace } from "./product/OverviewWorkspace";
import { AskWorkspace } from "./product/AskWorkspace";
import { RiskInbox } from "./product/RiskInbox";
import type { ProductView, RiskFilters } from "./product/types";
import { RISK_INBOX_LIMIT } from "./product/types";
import "./product/product.css";

// Demo recording defaults: high-signal only (P1–P2, medium+ confidence).
const DEFAULT_FILTERS: RiskFilters = {
  kind: "all",
  confidence: "high-medium",
  priority: "P1-P2",
  team: "all",
  windowDays: 0
};
const PRIMARY_VIEWS: ProductView[] = ["overview", "risks", "ask", "graph"];
const PRODUCT_VIEWS: ProductView[] = [
  ...PRIMARY_VIEWS,
  "identities",
  "repairs",
  "imports",
  "actions",
  "settings"
];

function initialView(): ProductView {
  if (!window.location.pathname.startsWith("/app")) return "overview";
  const requested = new URL(window.location.href).searchParams.get("view");
  return PRODUCT_VIEWS.includes(requested as ProductView) ? (requested as ProductView) : "overview";
}

export function App() {
  const [view, setView] = useState<ProductView>(initialView);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string>();
  const [detailOpen, setDetailOpen] = useState(true);
  const { actions, updateAction } = useRiskActions();
  const { faultlines, gaps, ghosts, graph, health, snapshot } = useXraySnapshot(
    undefined,
    [],
    filters.windowDays
  );
  const lensError =
    faultlines.isError || gaps.isError || ghosts.isError
      ? [faultlines.error, gaps.error, ghosts.error]
          .filter(Boolean)
          .map((err) => (err instanceof Error ? err.message : "Lens request failed"))
          .join(" · ")
      : undefined;
  const risks = useMemo(
    () => buildRiskInbox(ghosts.data, faultlines.data, gaps.data),
    [faultlines.data, gaps.data, ghosts.data]
  );
  const inboxRisks = useMemo(() => risks.slice(0, RISK_INBOX_LIMIT), [risks]);
  const activeId = inboxRisks.some((risk) => risk.id === selectedId)
    ? selectedId
    : inboxRisks[0]?.id;
  const activeRisk = inboxRisks.find((risk) => risk.id === activeId);

  function navigate(next: ProductView) {
    const url = new URL(window.location.href);
    url.searchParams.set("view", next);
    window.history.replaceState({}, "", url);
    setView(next);
  }

  const shell = (
    <ProductShell
      health={health.data}
      healthState={health.isPending ? "loading" : health.isError ? "error" : "ready"}
      onView={navigate}
      snapshot={snapshot.data}
      view={PRIMARY_VIEWS.includes(view) ? view : "overview"}
    >
      {view === "overview" ? (
        <OverviewWorkspace
          health={health.data}
          onRisk={(id) => {
            setSelectedId(id);
            setDetailOpen(true);
            navigate("risks");
          }}
          onView={navigate}
          risks={inboxRisks}
          snapshot={snapshot.data}
          totalRiskCount={risks.length}
        />
      ) : view === "risks" ? (
        <div className={`risks-layout ${detailOpen && activeRisk ? "detail-is-open" : ""}`}>
          <RiskInbox
            error={lensError}
            filters={filters}
            loading={faultlines.isPending || gaps.isPending || ghosts.isPending}
            onFilters={(next) => {
              setFilters(next);
              setDetailOpen(false);
            }}
            onSearch={(value) => {
              setSearch(value);
              setDetailOpen(false);
            }}
            onSelect={(id) => {
              setSelectedId(id);
              setDetailOpen(true);
            }}
            risks={inboxRisks}
            search={search}
            selectedId={detailOpen ? activeId : undefined}
            totalAvailable={risks.length}
          />
          {detailOpen && activeRisk ? (
            <RiskDetail
              action={actions[activeRisk.id] ?? EMPTY_ACTION}
              onAction={(patch) => updateAction(activeRisk.id, patch)}
              onClose={() => setDetailOpen(false)}
              risk={activeRisk}
            />
          ) : null}
        </div>
      ) : view === "ask" ? (
        <AskWorkspace snapshotId={snapshot.data?.snapshot_id} />
      ) : view === "graph" ? (
        <ExploreWorkspace
          error={graph.isError ? (graph.error instanceof Error ? graph.error.message : "Graph failed") : undefined}
          graph={graph.data}
          loading={graph.isPending || snapshot.isPending}
          risks={inboxRisks}
        />
      ) : (
        <OverviewWorkspace
          health={health.data}
          onRisk={(id) => {
            setSelectedId(id);
            setDetailOpen(true);
            navigate("risks");
          }}
          onView={navigate}
          risks={inboxRisks}
          snapshot={snapshot.data}
          totalRiskCount={risks.length}
        />
      )}
    </ProductShell>
  );

  return shell;
}
