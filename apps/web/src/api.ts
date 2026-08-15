export type SnapshotResponse = {
  snapshot_id: string;
  dataset_id: string;
  node_count: number;
  edge_count: number;
  evidence_count: number;
  limitations: string[];
};

export type LensEnvelope<TFinding> = {
  snapshot_id: string;
  analysis_status: "complete" | "partial" | "unsupported";
  status_explanation: string;
  limitations: string[];
  findings: TFinding[];
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
  };
};

export type FaultlineFinding = {
  source_module_key: string;
  target_module_key: string;
  source_owner_key: string;
  target_owner_key: string;
  dependency_weight: number;
  communication_distance: number | null;
  tier: string;
  severity: number;
};

export type GapFinding = {
  phantom_key: string;
  expected_kind: string;
  reason: string;
  inferred_epoch: number | null;
  predecessor_keys: string[];
  successor_keys: string[];
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

export function getGhosts(snapshotId: string) {
  return requestJson<LensEnvelope<GhostFinding>>(
    `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/ghosts`
  );
}

export function getFaultlines(snapshotId: string) {
  return requestJson<LensEnvelope<FaultlineFinding>>(
    `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/faultlines`
  );
}

export function getGapPath(snapshotId: string) {
  return requestJson<LensEnvelope<GapFinding>>(
    `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/gap-paths`,
    {
      body: JSON.stringify({
        source_artifact_key: "artifact:code-change",
        target_artifact_key: "artifact:directive"
      }),
      method: "POST"
    }
  );
}
