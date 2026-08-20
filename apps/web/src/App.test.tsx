import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";

const evidence = { evidence_id: "evidence:demo", source_type: "git", source_uri: "fixture://demo", source_record_id: "commit-123", predicate: "dependency", subject_key: "module:payments-api", object_key: "module:ledger-worker", evidence_class: "observed", confidence: 100, content_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", redacted_excerpt: "payments-api and ledger-worker changed together" };
const envelope = { snapshot_id: "xray-demo-v1:fixture", analysis_status: "complete", status_explanation: "Complete", limitations: [], source: "fixture", degraded_reason: null, executed_query: null, what_if: null, comparison: null };
const responses: Record<string, object> = {
  "/api/v1/health": { status: "ok", read_only: true, imports_enabled: false, hydra: { status: "fallback", configured: false, database: null, uri: null, detail: "Using reference analytics.", graph_loaded: false, node_count: null, edge_count: null } },
  "/api/v1/snapshots/current": { snapshot_id: "xray-demo-v1:fixture", dataset_id: "xray-demo-v1", node_count: 17, edge_count: 30, evidence_count: 34, limitations: ["Synthetic fixture only"] },
  "/api/v1/snapshots/available": [{ name: "xray-demo-v1", kind: "fixture", dataset_id: "xray-demo-v1", active: true }],
  "/api/v1/snapshots/xray-demo-v1%3Afixture/graph": { snapshot_id: "xray-demo-v1:fixture", nodes: [{ key: "person:maya-chen", name: "Maya Chen", title: "Operations specialist", team: "Operations", official_size: 12, actual_size: 18, selected: true }, { key: "person:alex-rivera", name: "Alex Rivera", title: "Payments director", team: "Payments", official_size: 9, actual_size: 7, selected: false }], edges: [{ source: "person:maya-chen", target: "person:alex-rivera", strength: "strong" }] },
  "/api/v1/snapshots/xray-demo-v1%3Afixture/ghosts": { ...envelope, findings: [{ person_key: "person:maya-chen", display_name: "Maya Chen", role_rank: 1, structural_rank: 1, formal_rank: 9, rank_gap: 8, sampled_centrality: .231, communication_degree: 4, centrality_method: "exact", removal_impact: { reachable_pairs_before: 15, pairs_lost_without_person: 5, max_len: 4 }, evidence: [{ ...evidence, predicate: "person_profile" }] }] },
  "/api/v1/snapshots/xray-demo-v1%3Afixture/faultlines": { ...envelope, source: "hydradb", findings: [{ source_module_key: "module:payments-api", target_module_key: "module:ledger-worker", source_owner_key: "person:alex-rivera", target_owner_key: "person:theo-brooks", dependency_weight: 12, source_owner_confidence: 90, target_owner_confidence: 80, communication_distance: null, tier: "no_path", severity: 12, evidence: [evidence] }] },
  "/api/v1/snapshots/xray-demo-v1%3Afixture/gaps": { ...envelope, total_findings: 1, findings: [{ phantom_key: "artifact:missing-approval", expected_kind: "approval", reason: "required_sequence_step_missing", inferred_epoch: 1736003600, predecessor_keys: ["artifact:directive"], successor_keys: ["artifact:code-change"], window_position: "in_window", days_after_corpus_start: 12, evidence: [{ ...evidence, predicate: "gap_phantom" }] }] }
};

beforeEach(() => { localStorage.clear(); globalThis.fetch = async (input) => { const payload = responses[new URL(input.toString()).pathname]; return payload ? Response.json(payload) : new Response("not found", { status: 404 }); }; });
function renderApp() { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); render(<QueryClientProvider client={client}><App/></QueryClientProvider>); }

test("the product opens on a prioritized risk inbox with truthful runtime status", async () => {
  renderApp();
  expect(await screen.findAllByText("xray-demo-v1")).toHaveLength(2);
  expect(screen.getByText("Reference fallback")).toBeInTheDocument();
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
