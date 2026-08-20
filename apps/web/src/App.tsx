import { useMemo, useState } from "react";
import { useXraySnapshot } from "./queries";
import { buildRiskInbox } from "./product/riskModel";
import { ProductShell } from "./product/ProductShell";
import { RiskDetail } from "./product/RiskDetail";
import { ActionsWorkspace } from "./product/ActionsWorkspace";
import { EMPTY_ACTION, useRiskActions } from "./product/useRiskActions";
import { ImportsWorkspace } from "./product/ImportsWorkspace";
import { ExploreWorkspace } from "./product/ExploreWorkspace";
import { OverviewWorkspace } from "./product/OverviewWorkspace";
import { SettingsWorkspace } from "./product/SettingsWorkspace";
import { RiskInbox } from "./product/RiskInbox";
import type { ProductView, RiskFilters } from "./product/types";
import "./product/product.css";

// The bundled demo corpus is historical. A rolling default can make a healthy
// snapshot look empty, so the inbox opens on all available evidence.
const DEFAULT_FILTERS: RiskFilters = { kind: "all", confidence: "all", team: "all", windowDays: 0 };
export function App() {
  const [view, setView] = useState<ProductView>("risks");
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string>();
  const [detailOpen, setDetailOpen] = useState(true);
  const { actions, updateAction } = useRiskActions();
  const { faultlines, gaps, ghosts, graph, health, snapshot } = useXraySnapshot(undefined, [], filters.windowDays);
  const risks = useMemo(() => buildRiskInbox(ghosts.data, faultlines.data, gaps.data), [faultlines.data, gaps.data, ghosts.data]);
  const activeId = risks.some((risk) => risk.id === selectedId) ? selectedId : risks[0]?.id;
  const activeRisk = risks.find((risk) => risk.id === activeId);
  return <ProductShell health={health.data} onView={setView} snapshot={snapshot.data} view={view}>
    {view === "overview" ? <OverviewWorkspace actions={actions} health={health.data} onRisk={(id) => { setSelectedId(id); setDetailOpen(true); setView("risks"); }} onView={setView} risks={risks} snapshot={snapshot.data}/> : view === "risks" ? <div className={`risks-layout ${detailOpen && activeRisk ? "detail-is-open" : ""}`}><RiskInbox filters={filters} onFilters={(next) => { setFilters(next); setDetailOpen(false); }} onSearch={(value) => { setSearch(value); setDetailOpen(false); }} onSelect={(id) => { setSelectedId(id); setDetailOpen(true); }} risks={risks} search={search} selectedId={detailOpen ? activeId : undefined}/>{detailOpen && activeRisk ? <RiskDetail action={actions[activeRisk.id] ?? EMPTY_ACTION} onAction={(patch) => updateAction(activeRisk.id, patch)} onClose={() => setDetailOpen(false)} risk={activeRisk}/> : null}</div> : view === "graph" ? <ExploreWorkspace graph={graph.data} risks={risks}/> : view === "actions" ? <ActionsWorkspace actions={actions} onOpen={(id) => { setSelectedId(id); setDetailOpen(true); setView("risks"); }} risks={risks}/> : view === "imports" ? <ImportsWorkspace health={health.data} onDone={() => setView("risks")} snapshot={snapshot.data}/> : view === "settings" ? <SettingsWorkspace health={health.data} snapshot={snapshot.data}/> :
      <section className="product-placeholder"><h1>{view === "graph" ? "Explore graph" : view[0]?.toUpperCase() + view.slice(1)}</h1><p>This workspace is being upgraded in the next feature slice.</p></section>}
  </ProductShell>;
}
