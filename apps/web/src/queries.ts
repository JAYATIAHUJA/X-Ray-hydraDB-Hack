import { useQuery } from "@tanstack/react-query";
import { getCurrentSnapshot, getFaultlines, getGapPath, getGaps, getGhosts, getGraph, getHealth } from "./api";
import type { GapPathRequest } from "./api";

export function useXraySnapshot(
  gapRequest?: GapPathRequest,
  excludePeople: string[] = [],
  windowDays = 0
) {
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
    queryKey: ["ghosts", snapshotId, excludePeople, windowDays],
    queryFn: () => getGhosts(snapshotId ?? "", excludePeople, windowDays)
  });

  const gaps = useQuery({
    enabled: snapshotId !== undefined,
    queryKey: ["gaps", snapshotId],
    queryFn: () => getGaps(snapshotId ?? "")
  });

  const graph = useQuery({
    enabled: snapshotId !== undefined,
    queryKey: ["graph", snapshotId, windowDays],
    queryFn: () => getGraph(snapshotId ?? "", windowDays)
  });

  const faultlines = useQuery({
    enabled: snapshotId !== undefined,
    queryKey: ["faultlines", snapshotId, windowDays],
    queryFn: () => getFaultlines(snapshotId ?? "", windowDays)
  });

  const gapPath = useQuery({
    enabled: snapshotId !== undefined && gapRequest !== undefined,
    queryKey: ["gap-path", snapshotId, gapRequest],
    queryFn: () => getGapPath(snapshotId ?? "", gapRequest)
  });

  return { faultlines, gapPath, gaps, ghosts, graph, health, snapshot };
}
