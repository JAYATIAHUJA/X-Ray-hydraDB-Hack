export type SnapshotResponse = {
  snapshot_id: string;
  dataset_id: string;
  node_count: number;
  edge_count: number;
  evidence_count: number;
  limitations: string[];
};

export type HealthResponse = {
  status: string;
  hydra: {
    status: "fallback" | "live" | "offline";
    configured: boolean;
    database: string | null;
    uri: string | null;
    detail: string;
    graph_loaded: boolean;
    node_count: number | null;
    edge_count: number | null;
  };
};

export type WhatIfSummary = {
  excluded_person_keys: string[];
  sampled_pairs_before: number;
  sampled_pairs_after: number;
  pairs_lost: number;
  max_len: number;
};

export type EngineComparison = {
  engine_ms: number | null;
  client_ms: number;
  client_method: string;
  sampled_people: number;
  engine_round_trips: number;
  client_equivalent_round_trips: number;
};

export type LensEnvelope<TFinding> = {
  snapshot_id: string;
  analysis_status: "complete" | "partial" | "unsupported";
  status_explanation: string;
  limitations: string[];
  findings: TFinding[];
  source: "fixture" | "hydradb";
  degraded_reason: string | null;
  executed_query: {
    text: string;
    params: Record<string, unknown>;
    max_len: number | null;
    round_trips: number;
    engine_ms: number;
  } | null;
  what_if: WhatIfSummary | null;
  comparison: EngineComparison | null;
  total_findings?: number | null;
};

export type GraphNode = {
  key: string;
  name: string;
  title: string;
  team: string;
  official_size: number;
  actual_size: number;
  selected: boolean;
};

export type GraphEdge = {
  source: string;
  target: string;
  strength: "strong" | "medium" | "weak";
};

export type GraphResponse = {
  snapshot_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type EvidenceSummary = {
  evidence_id: string;
  source_type: string;
  source_uri: string;
  source_record_id: string;
  predicate: string;
  subject_key: string;
  object_key: string;
  evidence_class: string;
  confidence: number;
  content_sha256: string;
  redacted_excerpt: string;
};

export type GhostFinding = {
  person_key: string;
  display_name: string;
  role_rank: number;
  structural_rank: number;
  formal_rank: number;
  rank_gap: number;
  sampled_centrality: number;
  communication_degree: number;
  removal_impact: {
    reachable_pairs_before: number;
    pairs_lost_without_person: number;
    max_len: number;
  } | null;
  evidence: EvidenceSummary[];
};

export type FaultlineFinding = {
  source_module_key: string;
  target_module_key: string;
  source_owner_key: string;
  target_owner_key: string;
  dependency_weight: number;
  source_owner_confidence: number;
  target_owner_confidence: number;
  communication_distance: number | null;
  tier: string;
  severity: number;
  bridge?: string[] | null;
  evidence: EvidenceSummary[];
};

export type GapChain = {
  node_keys: string[];
  phantom_indices: number[];
};

export type GapFinding = {
  phantom_key: string;
  expected_kind: string;
  reason: string;
  inferred_epoch: number | null;
  predecessor_keys: string[];
  successor_keys: string[];
  evidence: EvidenceSummary[];
  chain?: GapChain;
};

export type GapPathRequest = {
  source_artifact_key: string;
  target_artifact_key: string;
};

export type ImportPayload = {
  dataset_id: string;
  directory: Record<string, unknown>[];
  identity_map: Record<string, string>;
  mbox: string[];
  jira_csv?: string;
  git_log?: string;
  module_prefixes: Record<string, string>;
  slack_exports: Record<string, Record<string, unknown>[]>;
  channel_modules: Record<string, string[]>;
  message_modules: Record<string, string[]>;
  confluence_xml?: string;
  github_csv?: string;
};

export const DEFAULT_GAP_REQUEST: GapPathRequest = {
  source_artifact_key: "artifact:code-change",
  target_artifact_key: "artifact:directive"
};

const apiBaseUrl = import.meta.env.VITE_XRAY_API_BASE_URL ?? "http://127.0.0.1:8000";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: {
      "content-type": "application/json",
      ...init?.headers
    },
    ...init
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getCurrentSnapshot() {
  return requestJson<SnapshotResponse>("/api/v1/snapshots/current");
}

export function getHealth() {
  return requestJson<HealthResponse>("/api/v1/health");
}

export function getGraph(snapshotId: string, windowDays = 0) {
  return requestJson<GraphResponse>(
    `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/graph${windowDays > 0 ? `?window_days=${windowDays}` : ""}`
  );
}

export function getGhosts(snapshotId: string, exclude: string[] = [], windowDays = 0) {
  const query = exclude.map((key) => `exclude=${encodeURIComponent(key)}`).join("&");
  const windowQuery = windowDays > 0 ? `window_days=${windowDays}` : "";
  const separator = query && windowQuery ? "&" : "";
  return requestJson<LensEnvelope<GhostFinding>>(
    `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/ghosts${query || windowQuery ? `?${query}${separator}${windowQuery}` : ""}`
  );
}

export function getGaps(snapshotId: string, limit = 100) {
  return requestJson<LensEnvelope<GapFinding>>(
    `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/gaps?limit=${limit}`
  );
}

export function getFaultlines(snapshotId: string, windowDays = 0) {
  return requestJson<LensEnvelope<FaultlineFinding>>(
    `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/faultlines${windowDays > 0 ? `?window_days=${windowDays}` : ""}`
  );
}

export function getGapPath(snapshotId: string, request: GapPathRequest = DEFAULT_GAP_REQUEST) {
  return requestJson<LensEnvelope<GapFinding>>(
    `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/gap-paths`,
    {
      body: JSON.stringify(request),
      method: "POST"
    }
  );
}

export async function getRiskReport(snapshotId: string) {
  const response = await fetch(
    `${apiBaseUrl}/api/v1/snapshots/${encodeURIComponent(snapshotId)}/risk-report`
  );
  if (!response.ok) {
    throw new Error(`Risk report request failed: ${response.status}`);
  }
  return response.text();
}

export function importSnapshot(payload: ImportPayload) {
  return requestJson<SnapshotResponse>("/api/v1/snapshots/import", {
    body: JSON.stringify(payload),
    method: "POST"
  });
}
