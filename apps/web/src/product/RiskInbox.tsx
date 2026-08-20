import type { RiskFilters, RiskItem } from "./types";
import { Icon } from "./Icons";
import { riskKindLabel } from "./riskModel";

type Props = { risks: RiskItem[]; selectedId?: string; filters: RiskFilters; search: string; onFilters: (next: RiskFilters) => void; onSearch: (value: string) => void; onSelect: (id: string) => void };
export function RiskInbox({ risks, selectedId, filters, search, onFilters, onSearch, onSelect }: Props) {
  const teams = Array.from(new Set(risks.map((risk) => risk.team))).sort();
  const visible = risks.filter((risk) => {
    if (filters.kind !== "all" && risk.kind !== filters.kind) return false;
    if (filters.team !== "all" && risk.team !== filters.team) return false;
    if (filters.confidence === "high" && risk.confidence < 75) return false;
    if (filters.confidence === "medium" && (risk.confidence < 50 || risk.confidence >= 75)) return false;
    if (filters.confidence === "low" && risk.confidence >= 50) return false;
    const needle = search.trim().toLowerCase();
    return !needle || `${risk.title} ${risk.affectedArea} ${risk.team}`.toLowerCase().includes(needle);
  });
  return <section className="risk-inbox" aria-labelledby="risk-inbox-title">
    <header className="workspace-heading"><div><h1 id="risk-inbox-title">Risk inbox</h1><p>Prioritized coordination risks from the active evidence snapshot.</p></div>
      <label className="risk-search"><Icon name="search"/><span className="sr-only">Search risks</span><input placeholder="Search risks, services, teams…" value={search} onChange={(event) => onSearch(event.target.value)}/><kbd>⌘ K</kbd></label>
    </header>
    <div className="risk-filters" aria-label="Risk filters">
      <label><span>Risk type</span><select value={filters.kind} onChange={(event) => onFilters({ ...filters, kind: event.target.value as RiskFilters["kind"] })}><option value="all">All types</option><option value="coordination">Uncoordinated dependency</option><option value="key-person">Key-person dependency</option><option value="missing-evidence">Missing decision evidence</option></select></label>
      <label><span>Team</span><select value={filters.team} onChange={(event) => onFilters({ ...filters, team: event.target.value })}><option value="all">All teams</option>{teams.map((team) => <option key={team}>{team}</option>)}</select></label>
      <label><span>Time window</span><select value={filters.windowDays} onChange={(event) => onFilters({ ...filters, windowDays: Number(event.target.value) })}><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option><option value={180}>Last 6 months</option><option value={0}>All time</option></select></label>
      <label><span>Confidence</span><select value={filters.confidence} onChange={(event) => onFilters({ ...filters, confidence: event.target.value as RiskFilters["confidence"] })}><option value="all">All confidence</option><option value="high">High · 75%+</option><option value="medium">Medium · 50–74%</option><option value="low">Low · under 50%</option></select></label>
      <button className="filter-button" type="button"><Icon name="filter"/> More filters</button>
    </div>
    <div className="risk-count"><strong>{visible.length} risks</strong><span>Sorted by priority and confidence</span></div>
    <div className="risk-table-wrap"><table className="risk-table"><thead><tr><th>Priority</th><th>Risk</th><th>Risk type</th><th>Affected area</th><th>Team</th><th>Confidence</th><th>Last observed</th></tr></thead><tbody>
      {visible.map((risk) => <tr aria-selected={risk.id === selectedId} key={risk.id} onClick={() => onSelect(risk.id)}>
        <td><button className={`priority priority-${risk.priority.toLowerCase()}`} onClick={() => onSelect(risk.id)} type="button">{risk.priority}</button></td>
        <td><button className="risk-title-button" onClick={() => onSelect(risk.id)} type="button">{risk.title}</button></td>
        <td><span className={`risk-type risk-type-${risk.kind}`}><i/>{riskKindLabel(risk.kind)}</span></td><td>{risk.affectedArea}</td><td>{risk.team}</td>
        <td><strong>{risk.confidence >= 75 ? "High" : risk.confidence >= 50 ? "Medium" : "Low"}</strong><small>{risk.confidence}%</small></td><td>{risk.lastObserved}</td>
      </tr>)}</tbody></table>
      {visible.length === 0 ? <div className="risk-empty"><Icon name="filter"/><h2>No risks match these filters</h2><p>Clear a filter or search another service.</p></div> : null}
    </div>
  </section>;
}
