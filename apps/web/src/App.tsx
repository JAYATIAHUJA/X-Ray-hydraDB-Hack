import { useMemo, useState } from "react";
import { faultlineRows, gapRows, Lens, links, people, queryText } from "./data";

const tabs: Array<{ id: Lens; label: string; sublabel: string; icon: string }> = [
  { id: "org", label: "Org", sublabel: "People & Structure", icon: "M8 3v4m0 0H5v4h6V7H8Zm0 0h8m0-4v4m0 0h-3v4h6V7h-3ZM8 15v-2m8 2v-2m-8 2H5v4h6v-4H8Zm8 0h-3v4h6v-4h-3Z" },
  { id: "faultlines", label: "Faultlines", sublabel: "Tension & Risk", icon: "M12 2 5 13h6l-1 9 7-12h-6l1-8Z" },
  { id: "gaps", label: "Gaps", sublabel: "Missing Links", icon: "M4 8V4h4m8 0h4v4M4 16v4h4m8 0h4v-4M9 9h6v6H9z" }
];

export function App() {
  const [activeLens, setActiveLens] = useState<Lens>("org");
  const [mode, setMode] = useState<"actual" | "official">("actual");
  const selected = people.find((person) => person.selected) ?? people[0];
  const graphLinks = useMemo(
    () =>
      links.map((link) => ({
        ...link,
        source: people.find((person) => person.key === link.source),
        target: people.find((person) => person.key === link.target)
      })),
    []
  );

  if (selected === undefined) {
    throw new Error("Fixture people are missing");
  }

  return (
    <main className="app-shell">
      <header className="topbar" aria-label="Application status">
        <div className="brand-mark" aria-hidden="true">X</div>
        <div>
          <h1>X-Ray</h1>
          <p>X-Ray Evidence Platform</p>
        </div>
        <div className="status-pill">Local fixture</div>
        <div className="topbar-metric healthy">Healthy</div>
        <div className="topbar-metric">Graph: 17 nodes / 29 edges</div>
        <div className="topbar-metric">HydraDB: fixture trace</div>
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
            <div className="scale">Low <span /> <span /> <span /> <span /> High</div>
            <label className="check"><input defaultChecked type="checkbox" /> Log scale node sizes</label>
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
              const size = mode === "actual" ? person.actualSize : person.officialSize;
              return (
                <button
                  className={person.selected ? "person-node selected" : "person-node"}
                  key={person.key}
                  style={{
                    "--node-size": `${size}px`,
                    left: `${person.x}%`,
                    top: `${person.y}%`
                  } as React.CSSProperties}
                  type="button"
                >
                  <span>{person.name}</span>
                  <small>{person.title}</small>
                </button>
              );
            })}
          </div>

          <div className="bottom-grid">
            <DataTable title="Faultlines" rows={faultlineRows} />
            <DataTable title="Gaps" rows={gapRows} />
          </div>
        </section>

        <aside className="detail-panel" aria-label="Selected finding details">
          <section className="selected-block">
            <span className="eyeline">Selected node</span>
            <h2>{selected.name}</h2>
            <p>{selected.title} / {selected.team}</p>
            <code>{selected.key}</code>
          </section>

          <section className="finding-block">
            <h3>Ghost</h3>
            <p>This person’s structural position is materially higher than formal rank.</p>
          </section>

          <section className="metric-grid">
            <Metric label="Actual centrality" value="0.231" detail="1st structural rank" />
            <Metric label="Rank gap" value="+8 places" detail="Formal rank: 10th" />
            <Metric label="Removal impact" value="5 pairs" detail="Lost within 4 hops" />
            <Metric label="Evidence limits" value="2 notes" detail="Synthetic fixture only" />
          </section>

          <details className="query-card" open>
            <summary>How HydraDB Answered This</summary>
            <pre>{queryText}</pre>
            <footer>
              <span>maxLen: 4</span>
              <span>resultLimit: 100</span>
              <span>status: complete</span>
            </footer>
          </details>
        </aside>
      </div>
    </main>
  );
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

function DataTable({ title, rows }: { title: string; rows: Array<Record<string, string>> }) {
  const keys = Object.keys(rows[0] ?? {});

  return (
    <section className="table-panel">
      <h3>{title}</h3>
      <table>
        <thead>
          <tr>{keys.map((key) => <th key={key}>{key}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              {keys.map((key) => <td key={key}>{row[key]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
