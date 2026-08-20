import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";

const evidence = { evidence_id: "evidence:demo", source_type: "git", source_uri: "fixture://demo", source_record_id: "commit-123", predicate: "dependency", subject_key: "module:payments-api", object_key: "module:ledger-worker", evidence_class: "observed", confidence: 100, content_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", redacted_excerpt: "payments-api and ledger-worker changed together" };
const envelope = { snapshot_id: "xray-demo-v1:fixture", analysis_status: "complete", status_explanation: "Complete", limitations: [], source: "fixture", degraded_reason: null, executed_query: null, what_if: null, comparison: null };
const responses: Record<string, object> = {
  "/api/v1/health": { status: "ok", read_only: true, imports_enabled: false, hydra: { status: "fallback", configured: false, database: null, uri: null, detail: "Using reference analytics.", graph_loaded: false, node_count: null, edge_count: null } },
  "/api/v1/snapshots/current": { snapshot_id: "xray-demo-v1:fixture", dataset_id: "xray-demo-v1", node_count: 20, edge_count: 35, evidence_count: 39, limitations: ["Synthetic fixture only"] },
  "/api/v1/snapshots/available": [{ name: "xray-demo-v1", kind: "fixture", dataset_id: "xray-demo-v1", active: true }],
  "/api/v1/snapshots/xray-demo-v1%3Afixture/graph": { snapshot_id: "xray-demo-v1:fixture", nodes: [{ key: "person:maya-chen", name: "Maya Chen", title: "Operations specialist", team: "Operations", official_size: 12, actual_size: 18, selected: true }, { key: "person:alex-rivera", name: "Alex Rivera", title: "Payments director", team: "Payments", official_size: 9, actual_size: 7, selected: false }], edges: [{ source: "person:maya-chen", target: "person:alex-rivera", strength: "strong" }] },
  "/api/v1/snapshots/xray-demo-v1%3Afixture/ghosts": { ...envelope, findings: [{ person_key: "person:maya-chen", display_name: "Maya Chen", role_rank: 1, structural_rank: 1, formal_rank: 9, rank_gap: 8, sampled_centrality: .231, communication_degree: 4, centrality_method: "exact", removal_impact: { reachable_pairs_before: 15, pairs_lost_without_person: 5, max_len: 4 }, evidence: [{ ...evidence, predicate: "person_profile" }] }] },
  "/api/v1/snapshots/xray-demo-v1%3Afixture/faultlines": { ...envelope, source: "hydradb", findings: [{ source_module_key: "module:payments-api", target_module_key: "module:ledger-worker", source_owner_key: "person:alex-rivera", target_owner_key: "person:theo-brooks", dependency_weight: 12, source_owner_confidence: 90, target_owner_confidence: 80, communication_distance: null, tier: "no_path", severity: 12, evidence: [evidence] }] },
  "/api/v1/snapshots/xray-demo-v1%3Afixture/gaps": { ...envelope, total_findings: 1, findings: [{ phantom_key: "artifact:missing-approval", expected_kind: "approval", reason: "required_sequence_step_missing", inferred_epoch: 1736003600, predecessor_keys: ["artifact:directive"], successor_keys: ["artifact:code-change"], window_position: "in_window", days_after_corpus_start: 12, evidence: [{ ...evidence, predicate: "gap_phantom" }] }] }
  ,"/api/v1/snapshots/xray-demo-v1%3Afixture/questions": { snapshot_id: "xray-demo-v1:fixture", question: "Which services are affected if ledger-worker changes?", intent: "dependency_impact", status: "answered", answer: "Payments Api depends on Ledger Worker and may be affected.", subject_key: "module:ledger-worker", person_keys: ["person:alex-rivera"], evidence_ids: ["evidence:demo"], paths: [["module:ledger-worker", "module:payments-api", "person:alex-rivera"]], confidence: 90, answer_kind: "multi_hop", reasoning: ["Matched Ledger Worker.", "Traversed incoming DEPENDS_ON relationships.", "Joined the dependent module to its owner."], limitations: ["Impact means reachability, not proof of an incident."], evidence: [evidence], source: "hydradb", degraded_reason: null, executed_query: { text: "MATCH (dependent:Module)-[r:DEPENDS_ON]->(changed:Module) RETURN dependent", params: {}, max_len: null, round_trips: 1, engine_ms: 4.2 }, engine_ms: 4.2, round_trips: 1 },
  "/api/v1/snapshots/xray-demo-v1%3Afixture/identity-candidates": [{ candidate_id: "candidate:sam-ratnaparkhi", proposed_person_key: "person:sam-ratnaparkhi", proposed_display_name: "Sam Ratnaparkhi", confidence: 88, signals: ["Same surname, first initial, and company email local-part", "Shared workspace, surname, and overlapping active dates"], members: [{ person_key: "person:sam-ratnaparkhi", display_name: "Sam Ratnaparkhi", source_identity: "sam@company.com", source_type: "directory" }, { person_key: "person:soham", display_name: "Soham Ratnaparkhi", source_identity: "@soham", source_type: "slack" }, { person_key: "person:s-ratnaparkhi", display_name: "S. Ratnaparkhi", source_identity: "S. Ratnaparkhi", source_type: "git" }], status: "pending", projected_node_reduction: 2, affected_edge_count: 3, duplicate_relationships_removed: 2, limitations: ["This is a suggested merge, not a confirmed identity fact.", "Accepting queues the decision for a future snapshot rebuild; it does not rewrite source exports."] }]
};

beforeEach(() => { localStorage.clear(); globalThis.fetch = async (input) => { const payload = responses[new URL(input.toString()).pathname]; return payload ? Response.json(payload) : new Response("not found", { status: 404 }); }; });
function renderApp() { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); render(<QueryClientProvider client={client}><App/></QueryClientProvider>); }

test("the product opens on a prioritized risk inbox with truthful runtime status", async () => {
  renderApp();
  expect(await screen.findAllByText("xray-demo-v1")).toHaveLength(2);
  expect(screen.getByText("Snapshot analytics")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Risk inbox" })).toBeInTheDocument();
  expect((await screen.findAllByText(/Payments Api depends on Ledger Worker/)).length).toBeGreaterThan(1);
  expect(screen.getAllByText("Uncoordinated dependency").length).toBeGreaterThan(1);
  expect(screen.getAllByText("Key-person dependency").length).toBeGreaterThan(1);
  expect(screen.getAllByText("Missing decision evidence").length).toBeGreaterThan(1);
});

test("risk filters and search narrow the inbox", async () => {
  renderApp(); const user = userEvent.setup(); await screen.findAllByText(/Payments Api depends on Ledger Worker/);
  await user.selectOptions(screen.getAllByRole("combobox")[0]!, "missing-evidence");
  expect(screen.getByText(/Missing Approval/)).toBeInTheDocument();
  expect(screen.queryByText(/Payments Api depends on Ledger Worker/)).not.toBeInTheDocument();
  await user.selectOptions(screen.getAllByRole("combobox")[0]!, "all"); await user.type(screen.getByPlaceholderText("Search risks, services, teams…"), "Maya");
  expect(screen.getByText(/Maya Chen/)).toBeInTheDocument(); expect(screen.queryByText(/Missing Approval/)).not.toBeInTheDocument();
});

test("sidebar navigation exposes the product workspace without changing pages", async () => {
  renderApp(); const user = userEvent.setup(); await screen.findAllByText("xray-demo-v1");
  await user.click(screen.getByRole("button", { name: "Explore graph" }));
  expect(screen.getByRole("heading", { name: "Explore graph" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Explore graph" })).toHaveAttribute("aria-current", "page");
  await user.click(screen.getByRole("button", { name: "Accessible list" }));
  expect(screen.getByRole("button", { name: "Maya Chen" })).toBeInTheDocument();
});

test("selecting a risk opens its evidence-backed explanation", async () => {
  renderApp(); const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: /Missing decision evidence: Missing Approval/ }));
  expect(screen.getByRole("heading", { name: "Missing decision evidence: Missing Approval." })).toBeInTheDocument();
  expect(screen.getByText("What this means")).toBeInTheDocument();
  await user.click(screen.getByRole("tab", { name: "Limitations" }));
  expect(screen.getByText("Read before acting")).toBeInTheDocument();
});

test("risk ownership changes persist into the actions queue", async () => {
  renderApp(); const user = userEvent.setup(); await screen.findAllByText(/Payments Api depends on Ledger Worker/);
  await user.selectOptions(screen.getByLabelText("Assignee"), "Platform team");
  await user.selectOptions(screen.getByLabelText("Risk status"), "mitigating");
  await user.click(screen.getByRole("button", { name: "Create issue draft" }));
  await user.click(screen.getByRole("button", { name: "Actions" }));
  expect(screen.getByRole("heading", { name: "Actions" })).toBeInTheDocument();
  expect(screen.getByText("Platform team")).toBeInTheDocument();
  expect(screen.getByText("mitigating")).toBeInTheDocument();
  expect(screen.getByText("Draft ready")).toBeInTheDocument();
});

test("imports explain setup and respect the read-only hosted mode", async () => {
  renderApp(); const user = userEvent.setup(); await screen.findAllByText("xray-demo-v1");
  await user.click(screen.getByRole("button", { name: "Imports" }));
  expect(screen.getByRole("heading", { name: "Import a workspace" })).toBeInTheDocument();
  expect(screen.getByText("Hosted demo is read-only")).toBeInTheDocument();
  expect(screen.getByLabelText("Workspace ID")).toBeDisabled();
  expect(screen.getByText("What improves each lens?")).toBeInTheDocument();
});

test("overview and settings explain the product and API runtime", async () => {
  renderApp(); const user = userEvent.setup(); await screen.findAllByText("xray-demo-v1");
  await user.click(screen.getByRole("button", { name: "Overview" }));
  expect(screen.getByRole("heading", { name: "Workspace overview" })).toBeInTheDocument();
  expect(screen.getByText("Runtime truth")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Open API & runtime guide" }));
  expect(screen.getByRole("heading", { name: "API & runtime" })).toBeInTheDocument();
  expect(screen.getByText("Useful endpoints")).toBeInTheDocument();
  expect(screen.getByText(/source: "hydradb"/)).toBeInTheDocument();
});

test("the risk search keyboard shortcut focuses the search field", async () => {
  renderApp(); const user = userEvent.setup(); const input = await screen.findByPlaceholderText("Search risks, services, teams…");
  await user.keyboard("{Control>}k{/Control}");
  expect(input).toHaveFocus();
});

test("Judge Mode returns a multi-hop answer with live query proof", async () => {
  renderApp(); const user = userEvent.setup(); await screen.findAllByText("xray-demo-v1");
  await user.click(screen.getByRole("button", { name: "Ask X-Ray" }));
  await user.click(screen.getByRole("button", { name: "Which services are affected if ledger-worker changes?" }));
  expect(await screen.findByRole("heading", { name: "Payments Api depends on Ledger Worker and may be affected." })).toBeInTheDocument();
  expect(screen.getByText("Evidence path")).toBeInTheDocument();
  expect(screen.getByText("hydradb")).toBeInTheDocument();
  expect(screen.getByText(/MATCH \(dependent:Module\)/)).toBeInTheDocument();
});

test("identity review explains a merge before asking for a decision", async () => {
  renderApp(); const user = userEvent.setup(); await screen.findAllByText("xray-demo-v1");
  await user.click(screen.getByRole("button", { name: "Identity review" }));
  expect(await screen.findByRole("heading", { name: "Identity review" })).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: "Sam Ratnaparkhi" })).toBeInTheDocument();
  expect(screen.getByText("@soham")).toBeInTheDocument();
  expect(screen.getByText("Human review required")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Accept merge" })).toBeInTheDocument();
});
