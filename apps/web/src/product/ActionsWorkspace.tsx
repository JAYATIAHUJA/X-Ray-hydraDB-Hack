import type { RiskItem } from "./types";
import { EMPTY_ACTION, type RiskActionMap } from "./useRiskActions";

export function ActionsWorkspace({ risks, actions, onOpen }: { risks: RiskItem[]; actions: RiskActionMap; onOpen: (riskId: string) => void }) {
  const tracked = risks.filter((risk) => actions[risk.id]);
  return <section className="actions-workspace"><header className="section-heading"><div><span className="eyebrow">Follow-through</span><h1>Actions</h1><p>Ownership and mitigation work created from evidence-backed risks.</p></div><div className="actions-summary"><strong>{tracked.length}</strong><span>tracked findings</span></div></header>
    {tracked.length ? <div className="actions-list">{tracked.map((risk) => { const action = actions[risk.id] ?? EMPTY_ACTION; return <article key={risk.id}><div><span className={`priority priority-${risk.priority.toLowerCase()}`}>{risk.priority}</span></div><div><button onClick={() => onOpen(risk.id)} type="button">{risk.title}</button><span>{risk.team} · {risk.affectedArea}</span></div><dl><div><dt>Owner</dt><dd>{action.assignee}</dd></div><div><dt>Status</dt><dd className={`status-${action.status}`}>{action.status}</dd></div><div><dt>Due</dt><dd>{action.dueDate || "Not set"}</dd></div><div><dt>Issue</dt><dd>{action.issueCreated ? "Draft ready" : "Not created"}</dd></div></dl></article>; })}</div> : <div className="actions-empty"><span>0</span><h2>No follow-up work yet</h2><p>Open a risk, assign an owner or change its status. It will appear here automatically.</p></div>}
  </section>;
}
