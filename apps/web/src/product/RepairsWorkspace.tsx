import { useEffect, useState } from "react";
import {
  getRepairs,
  decideRepair,
  verifyRepair,
  type RepairProposal
} from "../api";

export function RepairsWorkspace({ snapshotId }: { snapshotId?: string }) {
  const [items, setItems] = useState<RepairProposal[]>([]);
  const [activeId, setActiveId] = useState<string>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!snapshotId) return;
    setLoading(true);
    getRepairs(snapshotId)
      .then((rows) => {
        setItems(rows);
        setActiveId((current) => current ?? rows[0]?.repair_id);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Repair ledger failed"))
      .finally(() => setLoading(false));
  }, [snapshotId]);

  const active = items.find((item) => item.repair_id === activeId) ?? items[0];

  async function decide(decision: "approved" | "rejected") {
    if (!snapshotId || !active) return;
    setBusy(true);
    setError(undefined);
    try {
      const updated = await decideRepair(snapshotId, active.repair_id, decision);
      setItems((rows) => {
        const next = rows.filter((row) => row.repair_id !== updated.repair_id);
        return [...next, updated].sort((a, b) => a.repair_id.localeCompare(b.repair_id));
      });
      setActiveId(updated.repair_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Decision failed");
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    if (!snapshotId || !active) return;
    setBusy(true);
    setError(undefined);
    try {
      const result = await verifyRepair(snapshotId, active.repair_id);
      setItems((rows) =>
        rows.map((row) =>
          row.repair_id === result.repair_id
            ? { ...row, closed: result.closed, status: result.status }
            : row
        )
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Verify failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="repairs-workspace">
      <header className="section-heading">
        <div>
          <span className="eyebrow">Coordination obligations</span>
          <h1>Repair ledger</h1>
          <p>
            Propose non-personnel repairs from open gaps and faultlines, approve with a write token,
            then re-check the same lens to prove the finding closed.
          </p>
        </div>
        <div className="actions-summary">
          <strong>{items.filter((item) => item.closed).length}</strong>
          <span>closed</span>
        </div>
      </header>
      {error ? (
        <div className="identity-error" role="alert">
          {error}
        </div>
      ) : null}
      {loading ? (
        <div className="identity-empty">Loading repair proposals…</div>
      ) : !active ? (
        <div className="identity-empty">
          <h2>No open repairs</h2>
          <p>Activate demo-v2 or import a corpus with gaps/faultlines to populate the ledger.</p>
        </div>
      ) : (
        <div className="identity-layout">
          <aside className="identity-queue">
            <h2>Proposed repairs</h2>
            {items.map((item) => (
              <button
                aria-current={item.repair_id === active.repair_id ? "true" : undefined}
                key={item.repair_id}
                onClick={() => setActiveId(item.repair_id)}
                type="button"
              >
                <i>{item.verdict.slice(0, 1)}</i>
                <span>
                  <strong>{item.title}</strong>
                  <small>{item.finding_kind}</small>
                </span>
                <em className={`decision-${item.closed ? "accepted" : item.status}`}>{item.closed ? "closed" : item.status}</em>
              </button>
            ))}
          </aside>
          <main className="identity-review">
            <section className="identity-card">
              <div className="identity-card-title">
                <div>
                  <span>{itemKindLabel(active.finding_kind)}</span>
                  <h2>{active.title}</h2>
                  <code>{active.repair_kind}</code>
                </div>
                <strong>
                  {active.verdict}
                  <small>evidence verdict</small>
                </strong>
              </div>
              <p>{active.summary}</p>
            </section>
            <section className="identity-evidence">
              <h3>Finding key</h3>
              <ul>
                <li>{active.finding_key}</li>
              </ul>
            </section>
            <section className="identity-warning">
              <strong>Human approval required</strong>
              <p>{active.limitations.join(" ")}</p>
            </section>
            <footer className="identity-actions">
              <button disabled={busy || active.status === "rejected"} onClick={() => void decide("rejected")} type="button">
                Reject
              </button>
              <button disabled={busy || active.status === "approved" || active.closed} onClick={() => void decide("approved")} type="button">
                {busy ? "Working…" : "Approve repair"}
              </button>
              <button disabled={busy || active.status === "proposed"} onClick={() => void verify()} type="button">
                Re-check / prove closed
              </button>
            </footer>
          </main>
        </div>
      )}
    </section>
  );
}

function itemKindLabel(kind: RepairProposal["finding_kind"]) {
  return kind === "gap" ? "Missing evidence gap" : "Dependency faultline";
}
