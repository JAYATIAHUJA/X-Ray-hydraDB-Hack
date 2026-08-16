import { useQuery } from "@tanstack/react-query";
import { getCurrentSnapshot, getFaultlines, getGapPath, getGhosts, getGraph, getHealth } from "./api";
import type { GapPathRequest } from "./api";

export function useXraySnapshot(gapRequest?: GapPathRequest) {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: getHealth
  });

  const snapshot = useQuery({
    queryKey: ["snapshot", "current"],
    queryFn: getCurrentSnapshot
  });
  const snapshotId = snapshot.data?.snapshot_id;

  const ghosts = useQuery({
    enabled: snapshotId !== undefined,
    queryKey: ["ghosts", snapshotId],
    queryFn: () => getGhosts(snapshotId ?? "")
  });

  const graph = useQuery({
    enabled: snapshotId !== undefined,
    queryKey: ["graph", snapshotId],
    queryFn: () => getGraph(snapshotId ?? "")
  });

  const faultlines = useQuery({
    enabled: snapshotId !== undefined,
    queryKey: ["faultlines", snapshotId],
    queryFn: () => getFaultlines(snapshotId ?? "")
  });

  const gapPath = useQuery({
    enabled: snapshotId !== undefined,
    queryKey: ["gap-path", snapshotId, gapRequest],
    queryFn: () => getGapPath(snapshotId ?? "", gapRequest)
  });

  return { faultlines, gapPath, ghosts, graph, health, snapshot };
}
