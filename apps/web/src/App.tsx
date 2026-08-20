import { useMemo, useState } from "react";
import { useXraySnapshot } from "./queries";
import { buildRiskInbox } from "./product/riskModel";
import { ProductShell } from "./product/ProductShell";
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
  const { faultlines, gaps, ghosts, health, snapshot } = useXraySnapshot(undefined, [], filters.windowDays);
  const risks = useMemo(() => buildRiskInbox(ghosts.data, faultlines.data, gaps.data), [faultlines.data, gaps.data, ghosts.data]);
  const activeId = risks.some((risk) => risk.id === selectedId) ? selectedId : risks[0]?.id;
  return <ProductShell health={health.data} onView={setView} snapshot={snapshot.data} view={view}>
    {view === "risks" || view === "overview" ? <RiskInbox filters={filters} onFilters={setFilters} onSearch={setSearch} onSelect={setSelectedId} risks={risks} search={search} selectedId={activeId}/> :
      <section className="product-placeholder"><h1>{view === "graph" ? "Explore graph" : view[0]?.toUpperCase() + view.slice(1)}</h1><p>This workspace is being upgraded in the next feature slice.</p></section>}
  </ProductShell>;
}
