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
  "/api/v1/snapshots/xray-demo-v1%3Afixture/gaps": { ...envelope, total_findings: 1, findings: [{ phantom_key: "artifact:missing-approval", expected_kind: "approval", reason: "required_sequence_step_missing", inferred_epoch: 1736003600, predecessor_keys: ["artifact:directive"], successor_keys: ["artifact:code-change"], window_position: "in_window", days_after_corpus_start: 12, evidence: [{ ...evidence, predicate: "gap_phantom" }] }] },
  "/api/v1/snapshots/xray-demo-v1%3Afixture/questions": { snapshot_id: "xray-demo-v1:fixture", question: "Which services are affected if ledger-worker changes?", intent: "dependency_impact", status: "answered", answer: "Payments Api depends on Ledger Worker and may be affected.", subject_key: "module:ledger-worker", person_keys: ["person:alex-rivera"], evidence_ids: ["evidence:demo"], paths: [["module:ledger-worker", "module:payments-api", "person:alex-rivera"]], confidence: 90, answer_kind: "multi_hop", reasoning: ["Matched Ledger Worker.", "Traversed incoming DEPENDS_ON relationships.", "Joined the dependent module to its owner."], limitations: ["Impact means reachability, not proof of an incident."], evidence: [evidence], source: "hydradb", degraded_reason: null, executed_query: { text: "MATCH (dependent:Module)-[r:DEPENDS_ON]->(changed:Module) RETURN dependent", params: {}, max_len: null, round_trips: 1, engine_ms: 4.2 }, engine_ms: 4.2, round_trips: 1 }
};

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState({}, "", "/app?view=overview");
  globalThis.fetch = async (input) => {
    const payload = responses[new URL(input.toString()).pathname];
    return payload ? Response.json(payload) : new Response("not found", { status: 404 });
  };
});

function renderApp(path = "/app?view=overview") {
  window.history.replaceState({}, "", path);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>
  );
}

test("the product opens on overview with truthful runtime status", async () => {
  renderApp();
  expect((await screen.findAllByText("xray-demo-v1")).length).toBeGreaterThanOrEqual(2);
  expect(screen.getAllByText(/Snapshot analytics/).length).toBeGreaterThan(0);
  expect(screen.getByRole("heading", { name: "Overview" })).toBeInTheDocument();
  expect(screen.getByText("Runtime")).toBeInTheDocument();
});

test("risk inbox shows prioritized findings after navigation", async () => {
  renderApp("/app?view=risks");
  const user = userEvent.setup();
  expect(await screen.findByRole("heading", { name: "Risks" })).toBeInTheDocument();
  await user.selectOptions(screen.getByDisplayValue("P1–P2"), "all");
  await user.selectOptions(screen.getByDisplayValue("Medium+"), "all");
  expect((await screen.findAllByText(/Payments Api depends on Ledger Worker/)).length).toBeGreaterThan(0);
  expect(screen.getAllByText("Uncoordinated dependency").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Key-person dependency").length).toBeGreaterThan(0);
});

test("risk filters and search narrow the inbox", async () => {
  renderApp("/app?view=risks");
  const user = userEvent.setup();
  await user.selectOptions(screen.getByDisplayValue("P1–P2"), "all");
  await user.selectOptions(screen.getByDisplayValue("Medium+"), "all");
  await screen.findAllByText(/Payments Api depends on Ledger Worker/);
  await user.selectOptions(screen.getByDisplayValue("All types"), "missing-evidence");
  expect(screen.getByText(/Missing Approval/)).toBeInTheDocument();
  expect(screen.queryByText(/Payments Api depends on Ledger Worker/)).not.toBeInTheDocument();
  await user.selectOptions(screen.getByDisplayValue("Missing decision evidence"), "all");
  await user.type(screen.getByPlaceholderText("Search risks, services, teams…"), "Maya");
  expect(screen.getByText(/Maya Chen/)).toBeInTheDocument();
  expect(screen.queryByText(/Missing Approval/)).not.toBeInTheDocument();
});

test("sidebar navigation exposes the four demo workspaces", async () => {
  renderApp();
  const user = userEvent.setup();
  await screen.findAllByText("xray-demo-v1");
  expect(screen.queryByRole("button", { name: "Imports" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Actions" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Explore graph" }));
  expect(screen.getByRole("heading", { name: "Explore graph" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Explore graph" })).toHaveAttribute("aria-current", "page");
  await user.click(screen.getByRole("button", { name: "Accessible list" }));
  expect(screen.getByRole("button", { name: "Maya Chen" })).toBeInTheDocument();
});

test("selecting a risk opens its evidence-backed explanation", async () => {
  renderApp("/app?view=risks");
  const user = userEvent.setup();
  await user.selectOptions(screen.getByDisplayValue("P1–P2"), "all");
  await user.selectOptions(screen.getByDisplayValue("Medium+"), "all");
  await user.click(await screen.findByRole("button", { name: /Missing decision evidence: Missing Approval/ }));
  expect(screen.getByRole("heading", { name: "Missing decision evidence: Missing Approval." })).toBeInTheDocument();
  expect(screen.getByText("What this means")).toBeInTheDocument();
  await user.click(screen.getByRole("tab", { name: "Limitations" }));
  expect(screen.getByText("Read before acting")).toBeInTheDocument();
});

test("the risk search keyboard shortcut focuses the search field", async () => {
  renderApp("/app?view=risks");
  const user = userEvent.setup();
  const input = await screen.findByPlaceholderText("Search risks, services, teams…");
  await user.keyboard("{Control>}k{/Control}");
  expect(input).toHaveFocus();
});

test("Ask X-Ray returns a multi-hop answer with live query proof", async () => {
  renderApp("/app?view=ask");
  const user = userEvent.setup();
  await screen.findAllByText("xray-demo-v1");
  const ask = await screen.findByRole("button", { name: "Ask" });
  await user.click(ask);
  expect(await screen.findByText(/Payments Api depends on Ledger Worker/)).toBeInTheDocument();
  expect(screen.getByText("Proof inspector")).toBeInTheDocument();
});
