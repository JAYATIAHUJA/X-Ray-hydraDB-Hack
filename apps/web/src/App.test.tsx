import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";

const gapRequests: unknown[] = [];
const evidence = {
  evidence_id: "evidence:demo",
  source_type: "git",
  source_uri: "fixture://demo",
  source_record_id: "commit-123",
  predicate: "dependency",
  subject_key: "module:payments-api",
  object_key: "module:ledger-worker",
  evidence_class: "observed",
  confidence: 100,
  content_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  redacted_excerpt: "payments-api and ledger-worker changed together"
};

const responses: Record<string, object> = {
  "/api/v1/health": {
    status: "ok",
    read_only: true,
    imports_enabled: false,
    hydra: {
      status: "fallback",
      configured: false,
      database: null,
      uri: null,
      detail: "XRAY_HYDRA_URI is not configured; using in-memory fixture analytics.",
      graph_loaded: false,
      node_count: null,
      edge_count: null
    }
  },
  "/api/v1/snapshots/current": {
    snapshot_id: "xray-demo-v1:fixture",
    dataset_id: "xray-demo-v1",
    node_count: 17,
    edge_count: 30,
    evidence_count: 34,
    limitations: ["Synthetic fixture only", "Absence does not establish deletion."]
  },
  "/api/v1/snapshots/xray-demo-v1%3Afixture/ghosts": {
    snapshot_id: "xray-demo-v1:fixture",
    analysis_status: "complete",
    status_explanation: "Fixture Ghost analysis completed with bounded path scoring.",
    limitations: [],
    source: "fixture",
    degraded_reason: null,
    executed_query: null,
    what_if: null,
    comparison: {
      engine_ms: null,
      client_ms: 12.5,
      client_method: "python_bounded_bfs_all_pairs",
      sampled_people: 10,
      engine_round_trips: 0,
      client_equivalent_round_trips: 45
    },
    findings: [
      {
        person_key: "person:maya-chen",
        display_name: "Maya Chen",
        role_rank: 1,
        structural_rank: 1,
        formal_rank: 9,
        rank_gap: 8,
        sampled_centrality: 0.231,
        communication_degree: 4,
        removal_impact: {
          reachable_pairs_before: 15,
          pairs_lost_without_person: 5,
          max_len: 4
        },
        evidence: [{ ...evidence, predicate: "person_profile", source_record_id: "person-maya" }]
      },
      {
        person_key: "person:alex-rivera",
        display_name: "Alex Rivera",
        role_rank: 4,
        structural_rank: 2,
        formal_rank: 1,
        rank_gap: -1,
        sampled_centrality: 0.042,
        communication_degree: 2,
        removal_impact: {
          reachable_pairs_before: 15,
          pairs_lost_without_person: 1,
          max_len: 4
        },
        evidence: [{ ...evidence, predicate: "person_profile", source_record_id: "person-alex" }]
      }
    ]
  },
  "/api/v1/snapshots/xray-demo-v1%3Afixture/graph": {
    snapshot_id: "xray-demo-v1:fixture",
    nodes: [
      {
        key: "person:maya-chen",
        name: "Maya Chen",
        title: "Operations specialist",
        team: "operations",
        official_size: 68,
        actual_size: 82,
        selected: true
      },
      {
        key: "person:alex-rivera",
        name: "Alex Rivera",
        title: "Payments director",
        team: "payments",
        official_size: 38,
        actual_size: 26,
        selected: false
      }
    ],
    edges: [
      {
        source: "person:alex-rivera",
        target: "person:maya-chen",
        strength: "strong"
      }
    ]
  },
  "/api/v1/snapshots/xray-demo-v1%3Afixture/faultlines": {
    snapshot_id: "xray-demo-v1:fixture",
    what_if: null,
    comparison: null,
    analysis_status: "complete",
    status_explanation: "Fixture Faultline analysis completed.",
    limitations: [],
    source: "hydradb",
    degraded_reason: null,
    executed_query: {
      text: "CALL algo.MSpaths({sourceLabel: 'Person'})",
      params: {},
      max_len: 4,
      round_trips: 1,
      engine_ms: 8.2
    },
    findings: [
      {
        source_module_key: "module:payments-api",
        target_module_key: "module:ledger-worker",
        source_owner_key: "person:alex-rivera",
        target_owner_key: "person:theo-brooks",
        dependency_weight: 12,
        communication_distance: null,
        tier: "no_path",
        severity: 12,
        evidence: [evidence]
      }
    ]
  },
  "/api/v1/snapshots/xray-demo-v1%3Afixture/gaps": {
    snapshot_id: "xray-demo-v1:fixture",
    analysis_status: "complete",
    status_explanation: "1 structurally missing records. Absence does not establish deletion.",
    limitations: ["Absence does not establish deletion."],
    source: "fixture",
    degraded_reason: null,
    executed_query: null,
    what_if: null,
    comparison: null,
    findings: [
      {
        phantom_key: "artifact:missing-approval",
        expected_kind: "approval",
        reason: "required_sequence_step_missing",
        inferred_epoch: 1736003600,
        predecessor_keys: ["artifact:directive"],
        successor_keys: ["artifact:code-change"],
        evidence: [{ ...evidence, predicate: "gap_phantom", source_record_id: "contract-approval" }]
      }
    ]
  },
  "/api/v1/snapshots/xray-demo-v1%3Afixture/gap-paths": {
    snapshot_id: "xray-demo-v1:fixture",
    analysis_status: "complete",
    status_explanation: "Fixture Gap analysis completed.",
    limitations: ["Absence does not establish deletion."],
    source: "hydradb",
    degraded_reason: null,
    executed_query: {
      text: "CALL algo.SPpaths({sourceNode: $source_id})",
      params: { source_id: 1 },
      max_len: 8,
      round_trips: 1,
      engine_ms: 4.1
    },
    what_if: null,
    comparison: null,
    findings: [
      {
        phantom_key: "artifact:missing-approval",
        expected_kind: "approval",
        reason: "required_sequence_step_missing",
        inferred_epoch: 1736003600,
        predecessor_keys: ["artifact:directive"],
        successor_keys: ["artifact:code-change"],
        evidence: [{ ...evidence, predicate: "gap_phantom", source_record_id: "contract-approval" }],
        chain: {
          node_keys: ["artifact:code-change", "artifact:missing-approval", "artifact:directive"],
          phantom_indices: [1]
        }
      }
    ]
  }
};

beforeEach(() => {
  gapRequests.length = 0;
  globalThis.fetch = async (input, init) => {
    const url = new URL(input.toString());
    if (url.pathname.endsWith("/gap-paths") && typeof init?.body === "string") {
      gapRequests.push(JSON.parse(init.body) as unknown);
    }
    const payload = responses[url.pathname];
    if (payload === undefined) {
      return new Response("not found", { status: 404 });
    }
    return Response.json(payload);
  };
});

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false
      }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  );
}

test("the dashboard shows graph, KPIs and the selected person in one view", async () => {
  renderApp();

  expect(await screen.findByText("xray-demo-v1")).toBeInTheDocument();
  expect(await screen.findByText("live")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Load data" })).not.toBeInTheDocument();

  // Selected-node card on the graph.
  expect(await screen.findAllByText("Maya Chen")).not.toHaveLength(0);
  expect(await screen.findByText("Operations specialist")).toBeInTheDocument();
  expect(await screen.findByText("#1")).toBeInTheDocument();
  expect(await screen.findByText("#9")).toBeInTheDocument();
  expect(await screen.findAllByText("+8")).not.toHaveLength(0);

  // Three KPI tiles.
  expect(screen.getByText("Structural rank")).toBeInTheDocument();
  expect(screen.getByText("Faultlines", { selector: ".kpi span" })).toBeInTheDocument();
  expect(screen.getByText("Gaps", { selector: ".kpi span" })).toBeInTheDocument();
  expect(screen.getByText("#1 structural · #9 formal")).toBeInTheDocument();

  // Ghost tab content by default.
  expect(await screen.findByText("Bounded removal test")).toBeInTheDocument();
  expect(screen.getByText("0.231")).toBeInTheDocument();

  await waitFor(() =>
    expect(gapRequests).toContainEqual({
      source_artifact_key: "artifact:code-change",
      target_artifact_key: "artifact:directive"
    })
  );
});

test("lens tabs switch the right panel", async () => {
  renderApp();
  await screen.findAllByText("Maya Chen");

  await userEvent.click(screen.getByRole("button", { name: "Faultlines" }));
  expect(await screen.findByText(/co-changed 12/)).toBeInTheDocument();
  expect(screen.getByText(/Introduce alex-rivera and theo-brooks/)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Gaps" }));
  expect(screen.getByText(/Absence in the corpus is not proof of deletion/)).toBeInTheDocument();
  expect(await screen.findAllByText(/missing-approval/)).not.toHaveLength(0);

  // Query toggle shows the executed HydraDB query for the active lens.
  await userEvent.click(screen.getByRole("button", { name: /Show HydraDB query/ }));
  expect(await screen.findByText("CALL algo.SPpaths({sourceNode: $source_id})")).toBeInTheDocument();
});

test("the Official / Actual toggle and what-if removal both work", async () => {
  renderApp();
  await screen.findAllByText("Maya Chen");

  const official = screen.getByRole("button", { name: "Official" });
  await userEvent.click(official);
  expect(official).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("Sized by job title")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /Remove from the graph/ }));
  expect(await screen.findByRole("button", { name: /Put back in the graph/ })).toBeInTheDocument();
});

test("question failures replace stale answers with a visible error", async () => {
  const fallbackFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    const url = new URL(input.toString());
    if (url.pathname.endsWith("/questions")) {
      return Response.json({ detail: "Question service unavailable" }, { status: 503 });
    }
    return fallbackFetch(input, init);
  };
  renderApp();
  const user = userEvent.setup();

  await screen.findByText("xray-demo-v1");
  await user.click(screen.getByRole("button", { name: "Ask" }));

  expect(await screen.findByText("Question service unavailable")).toBeInTheDocument();
});
