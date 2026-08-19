import { useEffect, useState } from "react";
import type { GapFinding, GapPathRequest } from "../api";
import type { Lens } from "../data";

function requestForGap(finding: GapFinding): GapPathRequest | undefined {
  const source = finding.successor_keys[0];
  const target = finding.predecessor_keys[0];
  return source && target
    ? { source_artifact_key: source, target_artifact_key: target }
    : undefined;
}

export function useLensState() {
  const [lens, setLens] = useState<Lens>("org");
  const [mode, setMode] = useState<"actual" | "official">("actual");
  const [selectedNodeKey, setSelectedNodeKey] = useState<string | undefined>();
  const [selectedFaultlineIndex, setSelectedFaultlineIndex] = useState(0);
  const [selectedGapIndex, setSelectedGapIndex] = useState(0);
  const [gapRequest, setGapRequest] = useState<GapPathRequest | undefined>();
  const [excluded, setExcluded] = useState<string[]>([]);
  const [showQuery, setShowQuery] = useState(false);

  return {
    excluded,
    gapRequest,
    lens,
    mode,
    selectedFaultlineIndex,
    selectedGapIndex,
    selectedNodeKey,
    setExcluded,
    setGapRequest,
    setLens,
    setMode,
    setSelectedFaultlineIndex,
    setSelectedGapIndex,
    setSelectedNodeKey,
    setShowQuery,
    showQuery
  };
}

type LensSynchronization = {
  defaultSelectedKey: string | undefined;
  faultlineCount: number;
  gapRequest: GapPathRequest | undefined;
  gaps: GapFinding[];
  selectedFaultlineIndex: number;
  selectedGapIndex: number;
  selectedNodeKey: string | undefined;
  setGapRequest: (request: GapPathRequest) => void;
  setSelectedFaultlineIndex: (index: number) => void;
  setSelectedGapIndex: (index: number) => void;
  setSelectedNodeKey: (key: string) => void;
};

export function useLensSynchronization(state: LensSynchronization) {
  useEffect(() => {
    if (state.selectedNodeKey === undefined && state.defaultSelectedKey !== undefined) {
      state.setSelectedNodeKey(state.defaultSelectedKey);
    }
  }, [state.defaultSelectedKey, state.selectedNodeKey, state.setSelectedNodeKey]);

  useEffect(() => {
    if (state.selectedFaultlineIndex >= state.faultlineCount) {
      state.setSelectedFaultlineIndex(0);
    }
  }, [state.faultlineCount, state.selectedFaultlineIndex, state.setSelectedFaultlineIndex]);

  useEffect(() => {
    if (state.selectedGapIndex >= state.gaps.length) state.setSelectedGapIndex(0);
  }, [state.gaps.length, state.selectedGapIndex, state.setSelectedGapIndex]);

  useEffect(() => {
    const finding = state.gaps[state.selectedGapIndex];
    const next = finding && requestForGap(finding);
    if (
      next !== undefined &&
      (state.gapRequest === undefined ||
        state.gapRequest.source_artifact_key !== next.source_artifact_key ||
        state.gapRequest.target_artifact_key !== next.target_artifact_key)
    ) {
      state.setGapRequest(next);
    }
  }, [state.gapRequest, state.gaps, state.selectedGapIndex, state.setGapRequest]);
}
