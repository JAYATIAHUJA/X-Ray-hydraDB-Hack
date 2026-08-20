import { useEffect, useState } from "react";
import { Icon } from "./Icons";
import { riskKindLabel } from "./riskModel";
import type { RiskItem } from "./types";
import type { RiskAction } from "./useRiskActions";

type DetailTab = "overview" | "evidence" | "query" | "limitations";
const tabs: Array<{ id: DetailTab; label: string }> = [
  { id: "overview", label: "Overview" }, { id: "evidence", label: "Evidence" },
  { id: "query", label: "HydraDB query" }, { id: "limitations", label: "Limitations" }
];

export function RiskDetail({ risk, action, onAction, onClose }: { risk: RiskItem; action: RiskAction; onAction: (patch: Partial<RiskAction>) => void; onClose: () => void }) {
  const [tab, setTab] = useState<DetailTab>("overview");
  useEffect(() => setTab("overview"), [risk.id]);
  return <aside className="risk-detail" aria-label="Risk detail">
    <header className="detail-header"><button className="detail-close" aria-label="Close risk detail" onClick={onClose} type="button"><Icon name="close"/></button>
      <div className="detail-kicker"><span className={`priority priority-${risk.priority.toLowerCase()}`}>{risk.priority}</span><strong>{riskKindLabel(risk.kind)}</strong><small>{risk.sourceLabel}</small></div>
      <h2>{risk.title}</h2><div className="detail-tags"><span>{risk.affectedArea}</span><span>{risk.team}</span><span>{risk.lastObserved}</span></div>
    </header>
    <div className="detail-tabs" role="tablist" aria-label="Finding detail sections">{tabs.map((item) => <button aria-selected={tab === item.id} key={item.id} onClick={() => setTab(item.id)} role="tab" type="button">{item.label}</button>)}</div>
    <div className="detail-body">
      {tab === "overview" ? <><section><h3>What this means</h3><p>{risk.explanation}</p></section><section><h3>Potential impact</h3><p>{risk.impact}</p></section><div className="detail-metrics"><Metric label="Confidence" value={risk.confidence}/><Metric label="Data coverage" value={risk.dataCoverage}/></div><section><h3>Recommended next step</h3><p>{risk.recommendation}</p></section><EvidenceList risk={risk} compact/></> : null}
      {tab === "evidence" ? <EvidenceList risk={risk}/> : null}{tab === "query" ? <QueryPanel risk={risk}/> : null}{tab === "limitations" ? <Limitations risk={risk}/> : null}
      <section className="ownership-panel"><h3>Ownership</h3><div><label><span>Assignee</span><select aria-label="Assignee" value={action.assignee} onChange={(event) => onAction({ assignee: event.target.value })}><option>Unassigned</option><option>Platform team</option><option>Payments team</option><option>Engineering leadership</option></select></label><label><span>Status</span><select aria-label="Risk status" value={action.status} onChange={(event) => onAction({ status: event.target.value as RiskAction["status"] })}><option value="open">Open</option><option value="acknowledged">Acknowledged</option><option value="mitigating">Mitigating</option><option value="resolved">Resolved</option><option value="dismissed">Dismissed</option></select></label><label><span>Due date</span><input aria-label="Due date" type="date" value={action.dueDate} onChange={(event) => onAction({ dueDate: event.target.value })}/></label></div><div className="detail-actions"><button className="primary-action" onClick={() => onAction({ issueCreated: true, status: action.status === "open" ? "acknowledged" : action.status })} type="button">{action.issueCreated ? "Issue draft ready" : "Create issue draft"}</button><button onClick={() => onAction({ status: "dismissed" })} type="button">Dismiss</button></div><small>Demo changes are saved in this browser only; no external issue tracker is contacted.</small></section>
    </div>
  </aside>;
}
function Metric({ label, value }: { label: string; value: number }) { return <div className="detail-metric"><span>{label}</span><strong>{value}%</strong><div aria-hidden="true"><i style={{ width: `${value}%` }}/></div></div>; }
function EvidenceList({ risk, compact = false }: { risk: RiskItem; compact?: boolean }) {
  const evidence = compact ? risk.evidence.slice(0, 3) : risk.evidence;
  return <section className="evidence-section"><h3>Evidence ({risk.evidence.length})</h3>{evidence.length ? <ul className="evidence-list">{evidence.map((item) => <li key={item.evidence_id}><Icon name="database"/><div><strong>{item.source_type} / {item.predicate.replaceAll("_", " ")}</strong><span>{item.redacted_excerpt || item.source_record_id}</span><code>{item.evidence_class} · {item.confidence}% confidence</code></div></li>)}</ul> : <p>No supporting records were returned for this finding.</p>}</section>;
}
function QueryPanel({ risk }: { risk: RiskItem }) {
  if (!risk.query) return <section className="detail-empty"><Icon name="database"/><h3>No HydraDB query for this result</h3><p>This finding was computed by the transparent reference implementation. The engine status above tells you when HydraDB is actually active.</p></section>;
  return <section><h3>Executed query</h3><p>This is the exact query provenance returned by the API.</p><pre>{risk.query.text}</pre><dl className="query-facts"><div><dt>Round trips</dt><dd>{risk.query.round_trips}</dd></div><div><dt>Engine time</dt><dd>{risk.query.engine_ms.toFixed(1)} ms</dd></div><div><dt>Max path</dt><dd>{risk.query.max_len ?? "Not bounded"}</dd></div></dl></section>;
}
function Limitations({ risk }: { risk: RiskItem }) { return <section><h3>Read before acting</h3><p>These findings are decision support, not proof of failure or employee performance.</p>{risk.limitations.length ? <ul className="limitation-list">{risk.limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No additional limitations were returned by this analysis.</p>}</section>; }
