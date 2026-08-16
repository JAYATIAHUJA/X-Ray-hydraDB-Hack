import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";

const responses: Record<string, object> = {
  "/api/v1/health": {
    status: "ok",
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
        }
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
        }
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
        severity: 12
      }
    ]
  },
  "/api/v1/snapshots/xray-demo-v1%3Afixture/gap-paths": {
    snapshot_id: "xray-demo-v1:fixture",
    analysis_status: "complete",
    status_explanation: "Fixture Gap analysis completed.",
    limitations: [],
    source: "hydradb",
    degraded_reason: null,
    executed_query: {
      text: "CALL algo.SPpaths({sourceNode: $source_id})",
      params: { source_id: 1 },
      max_len: 8,
      round_trips: 1,
      engine_ms: 4.1
    },
    findings: [
      {
        phantom_key: "artifact:missing-approval",
        expected_kind: "approval",
        reason: "required_sequence_step_missing",
        inferred_epoch: 1736003600,
        predecessor_keys: ["artifact:directive"],
        successor_keys: ["artifact:code-change"]
      }
    ]
  }
};

beforeEach(() => {
  globalThis.fetch = async (input) => {
    const url = new URL(input.toString());
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

test("renders the three-lens shell from API responses", async () => {
  renderApp();

  expect(screen.getByRole("heading", { name: "X-Ray" })).toBeInTheDocument();
  expect(screen.getByText("Loading")).toBeInTheDocument();
  expect(await screen.findByText("Graph: 17 nodes / 30 edges")).toBeInTheDocument();
  expect(await screen.findByText("HydraDB: fallback")).toBeInTheDocument();
  expect(await screen.findAllByText("Maya Chen")).toHaveLength(2);
  expect(await screen.findByText("Operations specialist / operations")).toBeInTheDocument();
  const alexNode = screen.getByRole("button", { name: /Alex Rivera/ });
  expect(alexNode).toBeInTheDocument();
  expect(alexNode).toHaveAttribute("aria-pressed", "false");
  expect(await screen.findByText("0.231")).toBeInTheDocument();
  expect(await screen.findByText("payments-api → ledger-worker")).toBeInTheDocument();
  expect(await screen.findByText("missing-approval")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /Faultlines/ }));

  expect(screen.getByRole("button", { name: /Faultlines/ })).toHaveAttribute("aria-current", "page");
  expect(screen.getByText("CALL algo.MSpaths({sourceLabel: 'Person'})")).toBeInTheDocument();

  await userEvent.click(alexNode);

  expect(alexNode).toHaveAttribute("aria-pressed", "true");
  expect(await screen.findByText("Payments director / payments")).toBeInTheDocument();
  expect(screen.getByText("person:alex-rivera")).toBeInTheDocument();
  expect(screen.getByText("0.042")).toBeInTheDocument();
  expect(screen.getByText("-1 places")).toBeInTheDocument();
});
