import { useQuery } from "@tanstack/react-query";
import { getCurrentSnapshot, getHealth } from "./api";

export function Landing() {
  const snapshot = useQuery({ queryKey: ["landing-snapshot"], queryFn: getCurrentSnapshot });
  const health = useQuery({ queryKey: ["landing-health"], queryFn: getHealth });
  const data = snapshot.data;

  return (
    <main className="landing-shell">
      <header className="landing-nav">
        <span className="brand-mark">X</span>
        <span>X-Ray Evidence Platform</span>
        <a href="/app">Open app</a>
      </header>
      <section className="landing-hero">
        <div>
          <span className="eyeline">Coordination-risk intelligence</span>
          <h1>X-Ray</h1>
          <p className="landing-tagline">
            The org chart says who reports to whom. X-Ray shows who keeps the work moving.
          </p>
          <div className="landing-actions">
            <a className="landing-primary" href="/app">Open X-Ray</a>
            <a href="/app#load-exports">Load your exports</a>
          </div>
        </div>
        <div className="landing-signal" aria-label="Live snapshot summary">
          <span>Live snapshot</span>
          <strong>{data?.dataset_id ?? "waiting for stack"}</strong>
          <p>
            {data ? `${data.node_count} nodes · ${data.edge_count} edges · ${data.evidence_count} evidence records` : "Start the API to load a real snapshot."}
          </p>
          <small>HydraDB: {health.data?.hydra.status ?? "pending"}</small>
        </div>
      </section>
      <section className="landing-lenses">
        <article>
          <span>01</span>
          <h2>Ghost</h2>
          <p>Find people whose sampled betweenness centrality in the communication graph exceeds their formal seniority rank. The org chart shows who manages whom; X-Ray shows who keeps the work moving.</p>
        </article>
        <article>
          <span>02</span>
          <h2>Faultlines</h2>
          <p>Find module dependencies whose owners have no bounded communication path (≤4 hops). Each finding includes a suggested shortest-introduction bridge and an evidence-backed severity score.</p>
        </article>
        <article>
          <span>03</span>
          <h2>Gaps</h2>
          <p>Find required evidence steps that are absent from the corpus — either from sequence contracts or dangling thread parents. Absence does not establish deletion; the finding names the structural requirement.</p>
        </article>
      </section>
      <section className="landing-corpora">
        <h2>Shipped corpora</h2>
        <div className="corpus-grid">
          <div className="corpus-card">
            <span>demo</span>
            <strong>xray-demo</strong>
            <p>10-person synthetic org with planted Ghost, Faultline, and Gap findings. Runs without any external service.</p>
          </div>
          <div className="corpus-card">
            <span>synthetic</span>
            <strong>synth-500</strong>
            <p>500-person synthetic org with ground-truth labels. Evaluated at 1.0 faultline/gap precision+recall, 0.933 ghost overlap.</p>
          </div>
          <div className="corpus-card">
            <span>real corpus</span>
            <strong>kafka-2025q2</strong>
            <p>Apache Kafka Mar–Jun 2025 git log and mailing list, processed through the export adapters. Ships in <code>data/snapshots/</code>.</p>
          </div>
        </div>
      </section>
      <footer className="landing-footer">
        Evidence-backed graph analysis · self-hosted HydraDB · Apache-2.0
        {" · "}
        <a href="/app" style={{ color: "inherit" }}>Open app →</a>
      </footer>
    </main>
  );
}
