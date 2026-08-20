import { useEffect, useRef } from "react";
import type { RiskFilters, RiskItem } from "./types";
import { RISK_INBOX_LIMIT } from "./types";
import { Icon } from "./Icons";
import { riskKindLabel } from "./riskModel";

type Props = {
  risks: RiskItem[];
  selectedId?: string;
  filters: RiskFilters;
  search: string;
  loading?: boolean;
  error?: string;
  totalAvailable?: number;
  onFilters: (next: RiskFilters) => void;
  onSearch: (value: string) => void;
  onSelect: (id: string) => void;
};

export function RiskInbox({
  risks,
  selectedId,
  filters,
  search,
  loading = false,
  error,
  totalAvailable,
  onFilters,
  onSearch,
  onSelect
}: Props) {
  const searchRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    globalThis.addEventListener("keydown", focusSearch);
    return () => globalThis.removeEventListener("keydown", focusSearch);
  }, []);

  const teams = Array.from(new Set(risks.map((risk) => risk.team))).sort();
  const visible = risks.filter((risk) => {
    if (filters.kind !== "all" && risk.kind !== filters.kind) return false;
    if (filters.team !== "all" && risk.team !== filters.team) return false;
    if (filters.priority === "P1" && risk.priority !== "P1") return false;
    if (filters.priority === "P1-P2" && risk.priority !== "P1" && risk.priority !== "P2") return false;
    if (filters.confidence === "high" && risk.confidence < 75) return false;
    if (filters.confidence === "medium" && (risk.confidence < 50 || risk.confidence >= 75)) return false;
    if (filters.confidence === "low" && risk.confidence >= 50) return false;
    if (filters.confidence === "high-medium" && risk.confidence < 50) return false;
    const needle = search.trim().toLowerCase();
    return !needle || `${risk.title} ${risk.affectedArea} ${risk.team}`.toLowerCase().includes(needle);
  });

  const cappedNote =
    typeof totalAvailable === "number" && totalAvailable > RISK_INBOX_LIMIT
      ? `Showing top ${RISK_INBOX_LIMIT} of ${totalAvailable}`
      : null;

  return (
    <section className="risk-inbox" aria-labelledby="risk-inbox-title">
      <header className="workspace-heading">
        <div>
          <h1 id="risk-inbox-title">Risks</h1>
          <p>Prioritized coordination signals from the active evidence snapshot.</p>
        </div>
        <label className="risk-search">
          <Icon name="search" />
          <span className="sr-only">Search risks</span>
          <input
            ref={searchRef}
            placeholder="Search risks, services, teams…"
            value={search}
            onChange={(event) => onSearch(event.target.value)}
          />
          <kbd>Ctrl K</kbd>
        </label>
      </header>
      <div className="risk-filters" aria-label="Risk filters">
        <label>
          <span>Priority</span>
          <select
            value={filters.priority}
            onChange={(event) =>
              onFilters({ ...filters, priority: event.target.value as RiskFilters["priority"] })
            }
          >
            <option value="P1">P1 only</option>
            <option value="P1-P2">P1–P2</option>
            <option value="all">All priorities</option>
          </select>
        </label>
        <label>
          <span>Risk type</span>
          <select
            value={filters.kind}
            onChange={(event) =>
              onFilters({ ...filters, kind: event.target.value as RiskFilters["kind"] })
            }
          >
            <option value="all">All types</option>
            <option value="coordination">Uncoordinated dependency</option>
            <option value="key-person">Key-person dependency</option>
            <option value="missing-evidence">Missing decision evidence</option>
          </select>
        </label>
        <label>
          <span>Team</span>
          <select
            value={filters.team}
            onChange={(event) => onFilters({ ...filters, team: event.target.value })}
          >
            <option value="all">All teams</option>
            {teams.map((team) => (
              <option key={team}>{team}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Confidence</span>
          <select
            value={filters.confidence}
            onChange={(event) =>
              onFilters({ ...filters, confidence: event.target.value as RiskFilters["confidence"] })
            }
          >
            <option value="high-medium">Medium+</option>
            <option value="high">High · 75%+</option>
            <option value="medium">Medium · 50–74%</option>
            <option value="low">Low · under 50%</option>
            <option value="all">All confidence</option>
          </select>
        </label>
      </div>
      <div className="risk-count">
        <strong>{loading ? "Loading analyses…" : `${visible.length} risks`}</strong>
        <span>{cappedNote ?? "Sorted by priority and confidence"}</span>
      </div>
      {error ? (
        <div className="workspace-error" role="alert">
          Could not load one or more lenses: {error}
        </div>
      ) : null}
      <div className="risk-table-wrap">
        <table className="risk-table">
          <thead>
            <tr>
              <th>Priority</th>
              <th>Risk</th>
              <th>Risk type</th>
              <th>Affected area</th>
              <th>Team</th>
              <th>Confidence</th>
              <th>Last observed</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((risk) => (
              <tr
                aria-selected={risk.id === selectedId}
                key={risk.id}
                onClick={() => onSelect(risk.id)}
              >
                <td data-label="Priority">
                  <button
                    className={`priority priority-${risk.priority.toLowerCase()}`}
                    onClick={() => onSelect(risk.id)}
                    type="button"
                  >
                    {risk.priority}
                  </button>
                </td>
                <td data-label="Risk">
                  <button className="risk-title-button" onClick={() => onSelect(risk.id)} type="button">
                    {risk.title}
                  </button>
                </td>
                <td data-label="Type">
                  <span className={`risk-type risk-type-${risk.kind}`}>
                    <i />
                    {riskKindLabel(risk.kind)}
                  </span>
                </td>
                <td data-label="Area">{risk.affectedArea}</td>
                <td data-label="Team">{risk.team}</td>
                <td data-label="Confidence">
                  <strong>
                    {risk.confidence >= 75 ? "High" : risk.confidence >= 50 ? "Medium" : "Low"}
                  </strong>
                  <small>{risk.confidence}%</small>
                </td>
                <td data-label="Observed">{risk.lastObserved}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && visible.length === 0 ? (
          <div className="risk-loading" role="status">
            <i />
            <i />
            <i />
            <span>Running the evidence lenses…</span>
          </div>
        ) : null}
        {!loading && !error && visible.length === 0 ? (
          <div className="risk-empty">
            <Icon name="filter" />
            <h2>No risks match these filters</h2>
            <p>Widen priority or confidence, or clear search.</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
