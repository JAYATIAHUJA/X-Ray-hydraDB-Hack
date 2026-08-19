import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type {
  EvidenceSummary,
  FaultlineFinding,
  GapFinding,
  GapPathRequest,
  GhostFinding,
  GraphNode,
  LensEnvelope
} from "./api";
import { activateSnapshot, askQuestion, getAvailableSnapshots, getRiskReport, importSnapshot } from "./api";
import type { AvailableSnapshot, ImportPayload, QuestionResponse } from "./api";
import type { Lens } from "./data";
import { Graph3D } from "./Graph3D";
import type { Graph3DEdge, Graph3DNode } from "./Graph3D";
import { useXraySnapshot } from "./queries";

const LENSES: Array<{ id: Lens; label: string; hint: string }> = [
  { id: "org", label: "Structural", hint: "structural rank × formal rank" },
  { id: "faultlines", label: "Faultlines", hint: "code depends, people don't talk" },
  { id: "gaps", label: "Gaps", hint: "records the graph requires" }
];

export function App() {
  const [lens, setLens] = useState<Lens>("org");
  const [mode, setMode] = useState<"actual" | "official">("actual");
  const [selectedNodeKey, setSelectedNodeKey] = useState<string | undefined>();
  const [selectedFaultlineIndex, setSelectedFaultlineIndex] = useState(0);
  const [selectedGapIndex, setSelectedGapIndex] = useState(0);
  const [gapRequest, setGapRequest] = useState<GapPathRequest | undefined>();
  const [excluded, setExcluded] = useState<string[]>([]);
  const [showImport, setShowImport] = useState(false);
  const [showQuery, setShowQuery] = useState(false);
  const [reportStatus, setReportStatus] = useState<string | null>(null);
  const [question, setQuestion] = useState("Who owns payments-api?");
  const [questionAnswer, setQuestionAnswer] = useState<QuestionResponse | null>(null);
  const [questionPending, setQuestionPending] = useState(false);

  const { faultlines, gapPath, gaps, ghosts, graph, health, snapshot } = useXraySnapshot(gapRequest, excluded, 0);

  const people = graph.data?.nodes ?? [];
  const defaultSelectedKey = people.find((p) => p.selected)?.key ?? people[0]?.key;
  const selectedKey = people.some((p) => p.key === selectedNodeKey) ? selectedNodeKey : defaultSelectedKey;
  const selected = people.find((p) => p.key === selectedKey);
  const ghostList = ghosts.data?.findings ?? [];
  const ghostFinding = ghostList.find((f) => f.person_key === selected?.key);
  const faultlineFindings = faultlines.data?.findings ?? [];
  const gapList = gaps.data?.findings ?? [];
  const gapChainFinding = gapPath.data?.findings.find((f) => f.chain !== undefined);
  const gapFindings = gapList.map((f) =>
    gapChainFinding && f.phantom_key === gapChainFinding.phantom_key ? gapChainFinding : f
  );
  const gapTotal = gaps.data?.total_findings ?? gapList.length;
  const topGhost = ghostList[0];
  const whatIf = ghosts.data?.what_if ?? null;
  const comparison = ghosts.data?.comparison ?? null;
  const selectedFaultline = faultlineFindings[selectedFaultlineIndex] ?? faultlineFindings[0];
  const selectedGap = gapFindings[selectedGapIndex] ?? gapFindings[0];
  const activeEnvelope: LensEnvelope<unknown> | undefined =
    lens === "org" ? ghosts.data : lens === "faultlines" ? faultlines.data : (gapPath.data ?? gaps.data);

  const connectedKeys = useMemo(() => {
    const keys = new Set<string>();
    (graph.data?.edges ?? []).forEach((e) => {
      keys.add(e.source);
      keys.add(e.target);
    });
    return keys;
  }, [graph.data?.edges]);

  const graphNodes = useMemo<Graph3DNode[]>(() => {
    const owners = new Set(faultlineFindings.flatMap((f) => [f.source_owner_key, f.target_owner_key]));
    // Only nodes that carry a finding get colour and a name; the rest recede into the background.
    // Cap the highlighted set so the canvas stays legible on real corpora.
    const topOwners = new Set(faultlineFindings.slice(0, 6).flatMap((f) => [f.source_owner_key, f.target_owner_key]));
    const focus = new Set<string>([
      ...ghostList.slice(0, 8).map((f) => f.person_key),
      ...ghostList.slice(0, 20).filter((f) => f.rank_gap >= 15).map((f) => f.person_key),
      ...topOwners
    ]);
    if (selectedKey) focus.add(selectedKey);
    const ghostKeys = new Set(ghostList.slice(0, 8).map((f) => f.person_key));
    return people
      .filter((p) => connectedKeys.has(p.key) || owners.has(p.key) || p.key === selectedKey)
      .map((p) => ({
        key: p.key,
        label: p.name,
        size: mode === "actual" ? p.actual_size : p.official_size,
        excluded: excluded.includes(p.key),
        focus: focus.has(p.key),
        role: topOwners.has(p.key) ? ("faultline" as const) : ghostKeys.has(p.key) ? ("ghost" as const) : owners.has(p.key) ? ("faultline" as const) : ("none" as const)
      }));
  }, [connectedKeys, excluded, faultlineFindings, ghostList, mode, people, selectedKey]);

  const graphEdges = useMemo<Graph3DEdge[]>(() => {
    const visible = new Set(graphNodes.map((n) => n.key));
    const comms: Graph3DEdge[] = (graph.data?.edges ?? [])
      .filter((e) => visible.has(e.source) && visible.has(e.target))
      .map((e) => ({ source: e.source, target: e.target, kind: e.strength }));
    const faults: Graph3DEdge[] = faultlineFindings
      .filter(
        (f) => visible.has(f.source_owner_key) && visible.has(f.target_owner_key) && f.source_owner_key !== f.target_owner_key
      )
      .map((f) => ({ source: f.source_owner_key, target: f.target_owner_key, kind: "faultline" as const }));
    return [...comms, ...faults];
  }, [faultlineFindings, graph.data?.edges, graphNodes]);

  const hasError = [snapshot, graph, ghosts, faultlines, gaps].some((q) => q.isError);
  const isLoading = snapshot.isPending || graph.isPending || ghosts.isPending;
  const noData = !snapshot.isPending && (snapshot.isError || (snapshot.data?.node_count ?? 0) === 0);

  useEffect(() => {
    if (selectedNodeKey === undefined && defaultSelectedKey !== undefined) setSelectedNodeKey(defaultSelectedKey);
  }, [defaultSelectedKey, selectedNodeKey]);
  useEffect(() => {
    if (selectedFaultlineIndex >= faultlineFindings.length) setSelectedFaultlineIndex(0);
  }, [faultlineFindings.length, selectedFaultlineIndex]);
  useEffect(() => {
    if (selectedGapIndex >= gapFindings.length) setSelectedGapIndex(0);
  }, [gapFindings.length, selectedGapIndex]);
  useEffect(() => {
    const finding = gapList[selectedGapIndex];
    if (finding === undefined) return;
    const next = requestForGap(finding);
    if (
      next !== undefined &&
      (gapRequest === undefined ||
        gapRequest.source_artifact_key !== next.source_artifact_key ||
        gapRequest.target_artifact_key !== next.target_artifact_key)
    ) {
      setGapRequest(next);
    }
  }, [gapList, gapRequest, selectedGapIndex]);

  async function exportRiskReport() {
    if (snapshot.data === undefined) return;
    setReportStatus("Preparing…");
    try {
      const report = await getRiskReport(snapshot.data.snapshot_id);
      const blob = new Blob([report], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${snapshot.data.dataset_id}-risk-report.md`;
      a.click();
      URL.revokeObjectURL(url);
      setReportStatus("Downloaded");
    } catch {
      setReportStatus("Unavailable");
    }
    globalThis.setTimeout(() => setReportStatus(null), 2500);
  }

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (snapshot.data === undefined || question.trim().length < 3) return;
    setQuestionPending(true);
    try {
      setQuestionAnswer(await askQuestion(snapshot.data.snapshot_id, question));
    } finally {
      setQuestionPending(false);
    }
  }

  if (showImport || noData) {
    return (
      <main className="app">
        <TopBar
          dataset={snapshot.data?.dataset_id}
          status={hasError ? "bad" : isLoading ? "wait" : "ok"}
          onImport={() => setShowImport(true)}
          onExport={exportRiskReport}
          canClose={!noData}
          onClose={() => setShowImport(false)}
        />
        <ImportScreen onDone={() => setShowImport(false)} />
      </main>
    );
  }

  return (
    <main className="app">
      <TopBar
        dataset={snapshot.data?.dataset_id}
        status={hasError ? "bad" : isLoading ? "wait" : "ok"}
        onImport={() => setShowImport(true)}
        onExport={exportRiskReport}
        reportStatus={reportStatus}
      />

      <div className="dash">
        {/* ── Left: graph ── */}
        <section className="dash-graph" aria-label="Communication graph">
          <div className="dash-graph-bar">
            <div className="segmented" role="group" aria-label="Node size mode">
              <button aria-pressed={mode === "official"} className={mode === "official" ? "segment active" : "segment"} onClick={() => setMode("official")} type="button">
                Official
              </button>
              <button aria-pressed={mode === "actual"} className={mode === "actual" ? "segment active" : "segment"} onClick={() => setMode("actual")} type="button">
                Actual
              </button>
            </div>
            <span className="dash-caption">{mode === "official" ? "Sized by job title" : "Sized by coordination load"}</span>
            <span className="dash-legend">
              <i className="lg-ghost" /> load-bearing
              <i className="lg-fault" /> faultline owner
              <i className="lg-sel" /> selected
              <i className="lg-edge" /> faultline
            </span>
          </div>

          <Graph3D nodes={graphNodes} edges={graphEdges} onSelect={setSelectedNodeKey} selectedKey={selectedKey} spin />

          {selected ? (
            <div className="node-card">
              <span className="eyeline">Selected</span>
              <strong>{selected.name}</strong>
              <small>{selected.title}</small>
              <dl>
                <div><dt>Structural</dt><dd>{ghostFinding ? `#${ghostFinding.structural_rank}` : "—"}</dd></div>
                <div><dt>Formal</dt><dd>{ghostFinding ? `#${ghostFinding.formal_rank}` : "—"}</dd></div>
                <div><dt>Gap</dt><dd className={ghostFinding && ghostFinding.rank_gap > 0 ? "pos" : ""}>{ghostFinding ? signed(ghostFinding.rank_gap) : "—"}</dd></div>
              </dl>
              {excluded.includes(selected.key) ? (
                <button className="btn-ghost" onClick={() => setExcluded([])} type="button">Put back in the graph</button>
              ) : (
                <button className="btn-ghost" onClick={() => setExcluded([selected.key])} type="button">Remove from the graph</button>
              )}
            </div>
          ) : null}

          {whatIf ? (
            <div className="whatif" role="status">
              <strong>Without {whatIf.excluded_person_keys.map((k) => nameFor(people, k)).join(", ")}</strong>
              <span>{whatIf.pairs_lost.toLocaleString()} of {whatIf.sampled_pairs_before.toLocaleString()} coordination paths disappear</span>
              <button onClick={() => setExcluded([])} type="button">Restore</button>
            </div>
          ) : null}
        </section>

        {/* ── Right: findings panel ── */}
        <aside className="dash-panel" aria-label="Findings">
          <form className="question-box" onSubmit={submitQuestion}>
            <label htmlFor="ontology-question">Ask the work graph</label>
            <div>
              <input id="ontology-question" onChange={(event) => setQuestion(event.target.value)} value={question} />
              <button disabled={questionPending} type="submit">{questionPending ? "…" : "Ask"}</button>
            </div>
            {questionAnswer ? (
              <p data-status={questionAnswer.status}>
                {questionAnswer.answer}
                {questionAnswer.evidence_ids.length > 0 ? <small>{questionAnswer.evidence_ids.length} evidence record(s)</small> : null}
              </p>
            ) : <small>Try “Who owns module X?” or “Who authored artifact Y?”</small>}
          </form>
          <div className="kpis">
            <button className={lens === "org" ? "kpi active" : "kpi"} onClick={() => setLens("org")} type="button">
              <span>Structural rank</span>
              <strong>{topGhost?.display_name ?? "—"}</strong>
              <small>{topGhost ? `#${topGhost.structural_rank} structural · #${topGhost.formal_rank} formal` : "computing"}</small>
            </button>
            <button className={lens === "faultlines" ? "kpi active" : "kpi"} onClick={() => setLens("faultlines")} type="button">
              <span>Faultlines</span>
              <strong>{faultlines.data ? faultlineFindings.length : "—"}</strong>
              <small>uncoordinated dependencies</small>
            </button>
            <button className={lens === "gaps" ? "kpi active" : "kpi"} onClick={() => setLens("gaps")} type="button">
              <span>Gaps</span>
              <strong>{gaps.data ? gapTotal : "—"}</strong>
              <small>missing records</small>
            </button>
          </div>

          <nav className="tabs" aria-label="Lens">
            {LENSES.map((t) => (
              <button aria-current={lens === t.id ? "page" : undefined} className={lens === t.id ? "tab active" : "tab"} key={t.id} onClick={() => setLens(t.id)} type="button">
                {t.label}
              </button>
            ))}
          </nav>

          <div className="panel-body">
            {lens === "org" ? (
              <GhostPanel list={ghostList} selectedKey={selectedKey} onSelect={setSelectedNodeKey} status={ghosts.data?.status_explanation} />
            ) : lens === "faultlines" ? (
              <FaultlinePanel list={faultlineFindings} index={selectedFaultlineIndex} onSelect={setSelectedFaultlineIndex} selected={selectedFaultline} status={faultlines.data?.status_explanation} />
            ) : (
              <GapPanel list={gapFindings} index={selectedGapIndex} onSelect={setSelectedGapIndex} selected={selectedGap} pending={gapPath.isPending && gapRequest !== undefined} status={gaps.data?.status_explanation} />
            )}
          </div>

          <footer className="panel-foot">
            <button className="foot-link" onClick={() => setShowQuery((v) => !v)} type="button">
              {showQuery ? "Hide" : "Show"} HydraDB query
            </button>
            <span>
              {comparison ? `engine ${comparison.engine_ms ?? "—"} ms · local reference ${comparison.client_ms.toFixed(1)} ms` : ""}
              {health.data ? ` · engine ${health.data.hydra.status}` : ""}
            </span>
          </footer>
          {showQuery && activeEnvelope?.executed_query ? (
            <pre className="query-pre">{activeEnvelope.executed_query.text}</pre>
          ) : showQuery ? (
            <p className="query-none">No live query for this lens ({activeEnvelope?.source ?? "pending"}).</p>
          ) : null}
        </aside>
      </div>
    </main>
  );
}

/* ── Panels ───────────────────────────────────────────────── */

function GhostPanel({ list, selectedKey, onSelect, status }: { list: GhostFinding[]; selectedKey?: string; onSelect: (k: string) => void; status?: string }) {
  if (list.length === 0) return <p className="muted">{status ?? "Waiting for the Ghost analysis."}</p>;
  const top = list[0]!;
  const sel = list.find((f) => f.person_key === selectedKey) ?? top;
  return (
    <>
      <div className="stat-row">
        <div>
          <span>Bounded removal test</span>
          <strong>{top.removal_impact ? top.removal_impact.pairs_lost_without_person.toLocaleString() : "—"}</strong>
          <small>of {top.removal_impact?.reachable_pairs_before.toLocaleString() ?? "—"} paths lost</small>
        </div>
        <div>
          <span>Selected centrality</span>
          <strong>{sel.sampled_centrality.toFixed(3)}</strong>
          <small>{sel.communication_degree} direct contacts</small>
        </div>
      </div>
      <ol className="rank-list">
        {list.slice(0, 8).map((f) => (
          <li key={f.person_key}>
            <button className={f.person_key === selectedKey ? "active" : ""} onClick={() => onSelect(f.person_key)} type="button">
              <span className="rank-pos">{f.structural_rank}</span>
              <span className="rank-name">{f.display_name}</span>
              <span className="rank-bar"><i style={{ width: `${bar(f, list)}%` }} /></span>
              <span className={f.rank_gap > 0 ? "rank-gap pos" : "rank-gap"}>{signed(f.rank_gap)}</span>
            </button>
          </li>
        ))}
      </ol>
      <Evidence records={sel.evidence} />
    </>
  );
}

function FaultlinePanel({ list, index, onSelect, selected, status }: { list: FaultlineFinding[]; index: number; onSelect: (i: number) => void; selected?: FaultlineFinding; status?: string }) {
  if (list.length === 0)
    return (
      <div className="muted">
        <p>{status ?? "No uncoordinated dependencies."}</p>
        <p style={{ marginTop: 8 }}>
          A faultline needs a <code>DEPENDS_ON</code> edge — two modules that co-change or explicitly reference each
          other — with no communication path between their owners. If the corpus carries no cross-module signal, this
          lens returns zero rather than inventing one. Faultlines are a coordination-debt map, not a bug oracle.
        </p>
      </div>
    );
  return (
    <>
      {selected ? (
        <div className="action-row">
          <span>Recommended</span>
          <strong>Introduce {suffix(selected.source_owner_key)} and {suffix(selected.target_owner_key)}</strong>
          {selected.bridge ? <small>via {selected.bridge.map(suffix).join(" → ")}</small> : null}
        </div>
      ) : null}
      <ul className="pair-list">
        {list.slice(0, 10).map((f, i) => (
          <li key={`${f.source_module_key}-${f.target_module_key}`}>
            <button className={i === index ? "pair active" : "pair"} onClick={() => onSelect(i)} type="button">
              <span className="pair-modules">{suffix(f.source_module_key)}<i />{suffix(f.target_module_key)}</span>
              <span className="pair-meta">co-changed {f.dependency_weight}× · {f.communication_distance === null ? "no path" : `${f.communication_distance} hops`}</span>
              <span className="pair-owners">{suffix(f.source_owner_key)} / {suffix(f.target_owner_key)}</span>
            </button>
          </li>
        ))}
      </ul>
      <Evidence records={selected?.evidence ?? []} />
    </>
  );
}

function GapPanel({ list, index, onSelect, selected, pending, status }: { list: GapFinding[]; index: number; onSelect: (i: number) => void; selected?: GapFinding; pending: boolean; status?: string }) {
  if (list.length === 0) return <p className="muted">{status ?? "No structurally missing records."}</p>;
  return (
    <>
      <p className="caveat">
        Absence in the corpus is not proof of deletion. <em>In window</em> = the parent should be in this export and
        isn&apos;t; <em>export boundary</em> = the reply sits in the first 30 days, so the parent probably predates the export.
      </p>
      {selected?.chain ? (
        <ol className="chain">
          {selected.chain.node_keys.map((k, i) => {
            const ph = selected.chain?.phantom_indices.includes(i) === true;
            return (
              <li className={ph ? "hop phantom" : "hop"} key={`${k}-${i}`}>
                <i />
                <code>{shortKey(k)}</code>
                {ph ? <small>missing</small> : null}
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="muted">{pending ? "Tracing the chain…" : selected ? `${suffix(selected.successor_keys[0] ?? "")} replies to a record that is not in the corpus.` : ""}</p>
      )}
      <ul className="gap-list">
        {list.slice(0, 10).map((f, i) => (
          <li key={f.phantom_key}>
            <button className={i === index ? "gap active" : "gap"} onClick={() => onSelect(i)} type="button">
              <span>
                {shortKey(f.phantom_key)}
                {f.window_position === "in_window" ? (
                  <b className="gap-badge in">in window · day {f.days_after_corpus_start ?? "?"}</b>
                ) : f.window_position === "export_boundary" ? (
                  <b className="gap-badge edge">export boundary</b>
                ) : null}
              </span>
              <small>{f.reason.replaceAll("_", " ")}</small>
            </button>
          </li>
        ))}
      </ul>
      <Evidence records={selected?.evidence ?? []} />
    </>
  );
}

function Evidence({ records }: { records: EvidenceSummary[] }) {
  const [open, setOpen] = useState(false);
  if (records.length === 0) return null;
  return (
    <div className="evidence">
      <button onClick={() => setOpen(!open)} type="button">
        {open ? "Hide" : "Show"} {records.length} source record{records.length === 1 ? "" : "s"}
      </button>
      {open ? (
        <ul>
          {records.slice(0, 5).map((r) => (
            <li key={r.evidence_id}>
              <span className="ev-type">{r.source_type}</span>
              <p>{r.redacted_excerpt || r.predicate}</p>
              <code>{r.source_record_id} · {r.confidence}%</code>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/* ── Chrome ───────────────────────────────────────────────── */

function TopBar({ dataset, status, onImport, onExport, reportStatus, canClose, onClose }: { dataset?: string; status: "ok" | "wait" | "bad"; onImport: () => void; onExport: () => void; reportStatus?: string | null; canClose?: boolean; onClose?: () => void }) {
  return (
    <header className="nav">
      <a className="nav-brand" href="/"><i />X-Ray</a>
      {dataset ? <span className="nav-dataset">{dataset}</span> : null}
      <span className={`nav-status ${status}`}>{status === "ok" ? "live" : status === "wait" ? "loading" : "degraded"}</span>
      <div className="nav-spacer" />
      {reportStatus ? <span className="nav-note">{reportStatus}</span> : null}
      {canClose ? (
        <button className="nav-link" onClick={onClose} type="button">Back to dashboard</button>
      ) : (
        <button className="nav-link" onClick={onImport} type="button">Load data</button>
      )}
      <button className="btn-primary" onClick={onExport} type="button">Export report</button>
    </header>
  );
}

function ImportScreen({ onDone }: { onDone: () => void }) {
  const [datasetId, setDatasetId] = useState("imported-snapshot");
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [slackFiles, setSlackFiles] = useState<File[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pick = (k: string) => (f: File | null) => setFiles((s) => ({ ...s, [k]: f }));
  async function readJson(f: File | null | undefined, fb: unknown) {
    if (!f) return fb;
    return JSON.parse(await f.text()) as unknown;
  }
  async function readText(f: File | null | undefined) {
    return f ? await f.text() : undefined;
  }

  async function run() {
    if (!files.directory) {
      setStatus("A directory.json is required — it lists the people.");
      return;
    }
    setBusy(true);
    setStatus("Building the graph…");
    try {
      const slackExports: Record<string, Record<string, unknown>[]> = {};
      for (const f of slackFiles) slackExports[f.name.replace(/\.json$/i, "")] = (await readJson(f, [])) as Record<string, unknown>[];
      const payload: ImportPayload = {
        dataset_id: datasetId.trim() || "imported-snapshot",
        directory: (await readJson(files.directory, [])) as Record<string, unknown>[],
        identity_map: (await readJson(files.identity, {})) as Record<string, string>,
        mbox: files.mbox ? [await files.mbox.text()] : [],
        jira_csv: await readText(files.jira),
        git_log: await readText(files.git),
        module_prefixes: (await readJson(files.modules, {})) as Record<string, string>,
        slack_exports: slackExports,
        channel_modules: (await readJson(files.channels, {})) as Record<string, string[]>,
        message_modules: (await readJson(files.messages, {})) as Record<string, string[]>,
        confluence_xml: await readText(files.confluence),
        github_csv: await readText(files.github)
      };
      const snap = await importSnapshot(payload);
      setStatus(`Imported ${snap.node_count.toLocaleString()} nodes and ${snap.edge_count.toLocaleString()} edges. Opening dashboard…`);
      globalThis.setTimeout(() => window.location.reload(), 600);
      onDone();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Import failed");
      setBusy(false);
    }
  }

  const [available, setAvailable] = useState<AvailableSnapshot[]>([]);
  const [switching, setSwitching] = useState<string | null>(null);
  useEffect(() => {
    getAvailableSnapshots().then(setAvailable).catch(() => setAvailable([]));
  }, []);
  async function open(name: string) {
    setSwitching(name);
    try {
      await activateSnapshot(name);
      window.location.reload();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Could not switch corpus");
      setSwitching(null);
    }
  }
  const labels: Record<string, { title: string; blurb: string }> = {
    demo: { title: "Demo org", blurb: "10 people, planted findings, no setup." },
    synth500: { title: "Synthetic 500", blurb: "Labelled ground truth — precision/recall are checkable." },
    "kafka-2025q2": { title: "Apache Kafka · Q2 2025", blurb: "Real public dev list + git + JIRA, 292 people." },
    "herb-2026": { title: "Salesforce HERB", blurb: "Official Track 01 corpus, 30 products, 5,126 people." }
  };

  return (
    <section className="import-screen">
      <div className="import-card">
        {available.length > 0 ? (
          <>
            <span className="eyeline">Open a shipped corpus</span>
            <h1>Start with data that&apos;s already here.</h1>
            <p className="import-lede">One click. No files. Every corpus below runs through the same pipeline as your own exports.</p>
            <div className="corpus-picker">
              {available.map((c) => {
                const meta = labels[c.name] ?? { title: c.dataset_id ?? c.name, blurb: c.kind === "fixture" ? "Bundled fixture." : "Ingested snapshot." };
                return (
                  <button className={c.active ? "corpus active" : "corpus"} disabled={switching !== null} key={c.name} onClick={() => open(c.name)} type="button">
                    <span>{c.kind === "fixture" ? "fixture" : "snapshot"}{c.active ? " · active" : ""}</span>
                    <strong>{meta.title}</strong>
                    <small>{meta.blurb}</small>
                    <em>{switching === c.name ? "Opening…" : c.active ? "Currently open" : "Open →"}</em>
                  </button>
                );
              })}
            </div>
            <hr className="import-divider" />
          </>
        ) : null}
        <span className="eyeline">Or load your own exports</span>
        <h2 className="import-h2">Build a snapshot from what you already have.</h2>
        <p className="import-lede">Everything runs locally. Only <b>Directory</b> is required — add whatever else you have; the more sources, the sharper the graph.</p>

        <div className="import-groups">
          <fieldset>
            <legend>Required</legend>
            <label>Snapshot name<input value={datasetId} onChange={(e) => setDatasetId(e.target.value)} /></label>
            <FileField label="Directory (people) · .json" accept=".json" onPick={pick("directory")} required />
            <FileField label="Identity map · .json" accept=".json" onPick={pick("identity")} />
          </fieldset>
          <fieldset>
            <legend>Conversations</legend>
            <label>Slack export · .json (multiple)<input accept=".json" multiple type="file" onChange={(e) => setSlackFiles(Array.from(e.target.files ?? []))} /></label>
            <FileField label="Email · .mbox" accept=".mbox,.txt" onPick={pick("mbox")} />
            <FileField label="Confluence space · .xml" accept=".xml" onPick={pick("confluence")} />
          </fieldset>
          <fieldset>
            <legend>Work</legend>
            <FileField label="git log · .log" accept=".log,.txt" onPick={pick("git")} />
            <FileField label="JIRA · .csv" accept=".csv" onPick={pick("jira")} />
            <FileField label="GitHub Issues · .csv" accept=".csv" onPick={pick("github")} />
          </fieldset>
          <fieldset>
            <legend>Mappings (optional)</legend>
            <FileField label="Module prefixes · .json" accept=".json" onPick={pick("modules")} />
            <FileField label="Channel → modules · .json" accept=".json" onPick={pick("channels")} />
            <FileField label="Message → modules · .json" accept=".json" onPick={pick("messages")} />
          </fieldset>
        </div>

        <div className="import-actions">
          <button className="btn-primary" disabled={busy} onClick={run} type="button">{busy ? "Working…" : "Build snapshot"}</button>
          {status ? <small>{status}</small> : null}
        </div>
      </div>
    </section>
  );
}

function FileField({ label, accept, onPick, required }: { label: string; accept: string; onPick: (f: File | null) => void; required?: boolean }) {
  const [name, setName] = useState<string | null>(null);
  return (
    <label className={name ? "file picked" : "file"}>
      <span>{label}{required ? " *" : ""}</span>
      <input accept={accept} type="file" onChange={(e) => { const f = e.target.files?.[0] ?? null; setName(f?.name ?? null); onPick(f); }} />
      <em>{name ?? "Choose file"}</em>
    </label>
  );
}

/* ── Helpers ──────────────────────────────────────────────── */

function bar(f: GhostFinding, all: GhostFinding[]) {
  const top = all[0]?.sampled_centrality ?? 1;
  return top <= 0 ? 4 : Math.max(4, Math.round((f.sampled_centrality / top) * 100));
}
function signed(n: number) {
  return n > 0 ? `+${n}` : String(n);
}
function suffix(v: string) {
  return v.split(":").at(-1) ?? v;
}
function shortKey(v: string) {
  const l = suffix(v);
  return l.length > 26 ? `${l.slice(0, 24)}…` : l;
}
function nameFor(people: GraphNode[], key: string) {
  return people.find((p) => p.key === key)?.name ?? suffix(key);
}
function requestForGap(f: GapFinding): GapPathRequest | undefined {
  const s = f.successor_keys[0];
  const t = f.predecessor_keys[0];
  return s === undefined || t === undefined ? undefined : { source_artifact_key: s, target_artifact_key: t };
}
