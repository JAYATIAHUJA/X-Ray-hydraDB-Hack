import { useEffect, useState } from "react";
import { decideIdentityCandidate, getIdentityCandidates, type IdentityCandidate } from "../api";

export function IdentityWorkbench({ snapshotId }: { snapshotId?: string }) {
  const [candidates, setCandidates] = useState<IdentityCandidate[]>([]);
  const [activeId, setActiveId] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();
  useEffect(() => {
    if (!snapshotId) return;
    setLoading(true);
    getIdentityCandidates(snapshotId).then((items) => { setCandidates(items); setActiveId((current) => current ?? items[0]?.candidate_id); }).catch((reason) => setError(reason instanceof Error ? reason.message : "Identity review failed")).finally(() => setLoading(false));
  }, [snapshotId]);
  const active = candidates.find((candidate) => candidate.candidate_id === activeId) ?? candidates[0];
  async function decide(decision: IdentityCandidate["status"]) {
    if (!snapshotId || !active) return;
    setSaving(true); setError(undefined);
    try { const updated = await decideIdentityCandidate(snapshotId, active.candidate_id, decision); setCandidates((items) => items.map((item) => item.candidate_id === updated.candidate_id ? updated : item)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Decision failed"); }
    finally { setSaving(false); }
  }
  return <section className="identity-workbench"><header className="identity-heading"><div><span>Entity resolution</span><h1>Identity review</h1><p>Review possible duplicate people before they change graph topology or risk scores.</p></div><div><strong>{candidates.filter((item) => item.status === "pending").length}</strong><span>Pending reviews</span></div></header>
    {error ? <div className="identity-error" role="alert">{error}</div> : null}
    {loading ? <div className="identity-empty">Loading review candidatesâ€¦</div> : !active ? <div className="identity-empty"><h2>No merge candidates</h2><p>The active snapshot did not emit any reviewable identity clusters.</p></div> : <div className="identity-layout"><aside className="identity-queue"><h2>Suggested merges</h2>{candidates.map((candidate) => <button aria-current={candidate.candidate_id === active.candidate_id ? "true" : undefined} key={candidate.candidate_id} onClick={() => setActiveId(candidate.candidate_id)} type="button"><i>{candidate.confidence}%</i><span><strong>{candidate.proposed_display_name}</strong><small>{candidate.members.length} source identities</small></span><em className={`decision-${candidate.status}`}>{candidate.status}</em></button>)}</aside>
      <main className="identity-review"><section className="identity-card"><div className="identity-card-title"><div><span>Suggested canonical person</span><h2>{active.proposed_display_name}</h2><code>{active.proposed_person_key}</code></div><strong>{active.confidence}%<small>match confidence</small></strong></div><div className="identity-members">{active.members.map((member, index) => <div key={member.person_key}><i>{member.display_name.slice(0, 1)}</i><span><strong>{member.display_name}</strong><code>{member.source_identity}</code><small>{member.source_type}</small></span>{index < active.members.length - 1 ? <b>+</b> : null}</div>)}<div className="identity-arrow">â†’</div><div className="identity-canonical"><i>{active.proposed_display_name.slice(0, 1)}</i><span><strong>One canonical person</strong><small>{active.proposed_display_name}</small></span></div></div></section>
        <section className="identity-evidence"><h3>Why X-Ray suggested this</h3><ul>{active.signals.map((signal) => <li key={signal}>{signal}</li>)}</ul></section>
        <section className="identity-impact"><div><span>Before</span><strong>{active.members.length} person nodes</strong><small>{active.affected_edge_count} attached relationships</small></div><i>â†’</i><div><span>After next rebuild</span><strong>1 canonical node</strong><small>{active.duplicate_relationships_removed} duplicate relationships removed</small></div></section>
        <section className="identity-warning"><strong>Human review required</strong><p>{active.limitations.join(" ")}</p></section>
        <footer className="identity-actions"><button disabled={saving} onClick={() => void decide("rejected")} type="button">Keep separate</button><button disabled={saving} onClick={() => void decide("accepted")} type="button">{saving ? "Savingâ€¦" : "Accept merge"}</button></footer>
      </main></div>}
  </section>;
}
