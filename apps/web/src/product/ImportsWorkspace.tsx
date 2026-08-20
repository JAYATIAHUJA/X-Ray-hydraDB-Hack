import type { HealthResponse, SnapshotResponse } from "../api";
import { useImportFlow } from "../hooks/useImportFlow";
import { Icon } from "./Icons";

const SOURCES = [
  { key: "directory", label: "People directory", accepts: ".json", required: true, purpose: "Names, teams and formal roles" },
  { key: "identity", label: "Identity map", accepts: ".json", purpose: "Connect emails and usernames safely" },
  { key: "slack", label: "Slack exports", accepts: ".json", multiple: true, purpose: "Observed coordination edges" },
  { key: "jira", label: "Jira issues", accepts: ".csv", purpose: "Work, ownership and decisions" },
  { key: "git", label: "Git log", accepts: ".txt,.log", purpose: "Module dependencies and changes" },
  { key: "github", label: "GitHub export", accepts: ".csv", purpose: "Reviews and collaboration" },
  { key: "confluence", label: "Confluence export", accepts: ".xml", purpose: "Decision and process evidence" }
] as const;

export function ImportsWorkspace({ health, snapshot, onDone }: { health?: HealthResponse; snapshot?: SnapshotResponse; onDone: () => void }) {
  const flow = useImportFlow(onDone); const enabled = health?.imports_enabled ?? false;
  return <section className="imports-workspace"><header className="section-heading"><div><span className="eyebrow">Data onboarding</span><h1>Import a workspace</h1><p>Start with the sample corpus or build a private snapshot from exports you control.</p></div><div className={`import-mode ${enabled ? "enabled" : "disabled"}`}><i/><strong>{enabled ? "Self-hosted import enabled" : "Hosted demo is read-only"}</strong></div></header>
    <div className="import-grid"><div className="import-primary"><div className="onboarding-steps" aria-label="Import steps"><span className="active"><b>1</b>Name</span><span><b>2</b>Sources</span><span><b>3</b>Review</span><span><b>4</b>Analyze</span></div>
      <div className="import-card"><div className="import-card-heading"><div><h2>Create evidence snapshot</h2><p>Files go to your configured X-Ray API. The hosted demo keeps imports disabled.</p></div><Icon name="database"/></div>
        <label className="dataset-field"><span>Workspace ID</span><input disabled={!enabled} value={flow.datasetId} onChange={(event) => flow.setDatasetId(event.target.value)} placeholder="acme-checkout-review"/></label>
        <div className="source-list">{SOURCES.map((source) => <label className="source-row" key={source.key}><div><strong>{source.label}{"required" in source && source.required ? <em>Required</em> : null}</strong><span>{source.purpose}</span></div><input accept={source.accepts} disabled={!enabled} multiple={"multiple" in source && source.multiple} onChange={(event) => source.key === "slack" ? flow.setSlackFiles(Array.from(event.target.files ?? [])) : flow.pick(source.key)(event.target.files?.[0] ?? null)} type="file"/></label>)}</div>
        <div className="privacy-note"><strong>Before you import</strong><p>Minimize the export, remove message bodies you do not need, and review identity mappings. X-Ray should analyze coordination evidence—not become an employee surveillance feed.</p></div>
        <button className="import-submit" disabled={!enabled || flow.busy} onClick={() => void flow.run()} type="button">{flow.busy ? "Building evidence graph…" : "Review and build snapshot"}</button>{flow.status ? <p className="import-status" role="status">{flow.status}</p> : null}
      </div></div>
      <aside className="import-aside"><div className="snapshot-card"><span className="eyebrow">Active now</span><h2>{snapshot?.dataset_id ?? "Loading workspace"}</h2><dl><div><dt>Nodes</dt><dd>{snapshot?.node_count ?? "—"}</dd></div><div><dt>Edges</dt><dd>{snapshot?.edge_count ?? "—"}</dd></div><div><dt>Evidence</dt><dd>{snapshot?.evidence_count ?? "—"}</dd></div></dl>{snapshot?.limitations.length ? <p>{snapshot.limitations.length} coverage limitations are disclosed in findings.</p> : <p>Snapshot reports complete coverage.</p>}</div>
        <div className="snapshot-card"><span className="eyebrow">Available corpora</span><h2>Open a prepared demo</h2>{flow.available.length ? <ul className="corpus-list">{flow.available.map((item) => <li key={item.name}><div><strong>{item.dataset_id ?? item.name}</strong><span>{item.kind}{item.active ? " · active" : ""}</span></div><button disabled={item.active || flow.switching !== null} onClick={() => void flow.open(item.name)} type="button">{flow.switching === item.name ? "Opening…" : item.active ? "Current" : "Open"}</button></li>)}</ul> : <p>No additional prepared corpora are exposed by this API.</p>}</div>
        <div className="coverage-guide"><h3>What improves each lens?</h3><ul><li><b>Ghosts</b><span>Directory + communication exports</span></li><li><b>Faultlines</b><span>Git modules + owners + communication</span></li><li><b>Gaps</b><span>Workflow contracts + issue/doc history</span></li></ul></div>
      </aside></div>
  </section>;
}
