import { useState } from "react";
import { askQuestion, type QuestionResponse } from "../api";
import { Icon } from "./Icons";

const EXAMPLES = [
  "Who owns payments-api now, and why did an older Jira record say Alex?",
  "Which services are affected if ledger-worker changes?",
  "Who approved the refund limit change?",
  "Who authored Directive?",
  "Who reviewed Directive?"
];
const displayKey = (key: string) => key.split(":").at(-1)?.replaceAll("-", " ") ?? key;

export function AskWorkspace({ snapshotId }: { snapshotId?: string }) {
  const [question, setQuestion] = useState(EXAMPLES[1]); const [result, setResult] = useState<QuestionResponse>(); const [busy, setBusy] = useState(false); const [error, setError] = useState<string>();
  async function run(nextQuestion = question) { if (!snapshotId || !nextQuestion.trim()) return; setBusy(true); setError(undefined); try { setResult(await askQuestion(snapshotId, nextQuestion.trim())); } catch (reason) { setError(reason instanceof Error ? reason.message : "Question failed"); } finally { setBusy(false); } }
  return <section className="ask-workspace"><header className="ask-heading"><h1>Ask X-Ray</h1><p>Ask deterministic questions over the evidence graph. Every supported answer cites its path and sources.</p></header>
    <div className="ask-composer"><label><span className="sr-only">Question</span><input value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void run(); }}/></label><button disabled={busy || !snapshotId} onClick={() => void run()} type="button">{busy ? "Reasoning…" : "Ask"}</button></div>
    <div className="ask-examples"><span>Try an example</span><div>{EXAMPLES.map((example) => <button key={example} onClick={() => { setQuestion(example); void run(example); }} type="button">{example}</button>)}</div></div>
    {error ? <div className="ask-error" role="alert">{error}</div> : null}
    {!result && !busy ? <div className="ask-intro"><Icon name="ask"/><h2>Reason over relationships, not similar text</h2><p>Ask about ownership, reverse dependency impact, authorship, review history, or a missing approval. Unsupported questions are refused instead of guessed.</p></div> : null}
    {busy ? <div className="ask-loading" role="status"><i/><i/><i/><span>Following typed graph relationships…</span></div> : null}
    {result && !busy ? <Answer result={result}/> : null}
  </section>;
}

function Answer({ result }: { result: QuestionResponse }) {
  const abstained = result.answer_kind === "abstention" || result.status !== "answered";
  const conflicts = result.conflicts ?? [];
  return <div className="answer-layout"><main className="answer-main"><section className={`answer-summary ${abstained ? "is-abstention" : ""}`}><div><span>{abstained ? "Refused to guess" : "Answer"}</span><small>{result.status.replaceAll("_", " ")}</small></div><h2>{result.answer}</h2><p>{abstained ? "X-Ray did not find enough typed evidence to make the requested claim." : "This answer is bounded to the active snapshot and the evidence below."}</p></section>
    {result.paths.length ? <section className="answer-section"><h3>Evidence path</h3><div className="answer-paths">{result.paths.map((path, index) => <div className="answer-path" key={`${path.join("-")}-${index}`}>{path.map((key, nodeIndex) => <span key={key}><b>{displayKey(key)}</b><small>{key.split(":")[0]}</small>{nodeIndex < path.length - 1 ? <i>→</i> : null}</span>)}</div>)}</div></section> : null}
    {conflicts.length ? <section className="answer-section conflict-section"><div className="section-title-row"><h3>Conflicting evidence</h3><span>{conflicts.length} records compared</span></div><div className="conflict-grid">{conflicts.map((item) => <article className={item.selected ? "is-selected" : "is-rejected"} key={`${item.source_type}-${item.source_record_id}`}><div><strong>{displayKey(item.person_key)}</strong><span>{item.selected ? "Trusted current" : "Superseded"}</span></div><dl><div><dt>Source</dt><dd>{item.source_type}</dd></div><div><dt>Record</dt><dd>{item.source_record_id}</dd></div><div><dt>Authority</dt><dd>{item.authority.replaceAll("_", " ")}</dd></div><div><dt>Valid until</dt><dd>{formatEpoch(item.valid_until_epoch)}</dd></div></dl><p>{item.reason}</p></article>)}</div>{result.trust_explanation ? <p className="trust-explanation"><b>Why this source won:</b> {result.trust_explanation}</p> : null}</section> : null}
    <section className="answer-section"><h3>Reasoning</h3><ol className="reasoning-list">{result.reasoning.map((step) => <li key={step}>{step}</li>)}</ol></section>
    <section className="answer-section"><h3>Supporting evidence ({result.evidence.length})</h3>{result.evidence.length ? <table className="answer-evidence"><thead><tr><th>Source</th><th>Predicate</th><th>Subject</th><th>Confidence</th></tr></thead><tbody>{result.evidence.map((item) => <tr key={item.evidence_id}><td>{item.source_type}</td><td>{item.predicate.replaceAll("_", " ")}</td><td>{displayKey(item.subject_key)}</td><td>{item.confidence}%</td></tr>)}</tbody></table> : <p className="no-evidence">No observed evidence record supports an answer.</p>}</section>
    {result.limitations.length ? <section className="answer-limitations"><h3>Read before acting</h3><ul>{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}</main><ProofInspector result={result}/></div>;
}
function formatEpoch(value: number | null) { return value === null ? "Still active" : new Intl.DateTimeFormat("en", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(value * 1000)); }
function ProofInspector({ result }: { result: QuestionResponse }) { return <aside className="proof-inspector"><h2>Proof inspector</h2><dl><div><dt>Source</dt><dd className={`proof-source source-${result.source}`}>{result.source}</dd></div><div><dt>Answer type</dt><dd>{result.answer_kind.replaceAll("_", " ")}</dd></div><div><dt>Confidence</dt><dd>{result.confidence === null ? "Not claimed" : `${result.confidence}%`}</dd></div><div><dt>Round trips</dt><dd>{result.round_trips}</dd></div><div><dt>Engine time</dt><dd>{result.engine_ms === null ? "Not measured" : `${result.engine_ms.toFixed(1)} ms`}</dd></div></dl><section><h3>Executed query</h3>{result.executed_query ? <pre>{result.executed_query.text}</pre> : <p>Reference analytics answered this question. Start the configured HydraDB runtime to produce live query proof.</p>}</section>{result.degraded_reason ? <section className="proof-degraded"><h3>Degraded execution</h3><p>{result.degraded_reason}</p></section> : null}</aside>; }
