import { useQuery } from "@tanstack/react-query";
import { getCurrentSnapshot, getFaultlines, getGapPath, getGhosts } from "./api";

export function useXraySnapshot() {
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

  const faultlines = useQuery({
    enabled: snapshotId !== undefined,
    queryKey: ["faultlines", snapshotId],
    queryFn: () => getFaultlines(snapshotId ?? "")
  });

  const gapPath = useQuery({
    enabled: snapshotId !== undefined,
    queryKey: ["gap-path", snapshotId],
    queryFn: () => getGapPath(snapshotId ?? "")
  });

  return { faultlines, gapPath, ghosts, snapshot };
}
