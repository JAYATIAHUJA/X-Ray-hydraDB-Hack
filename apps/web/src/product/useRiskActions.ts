import { useEffect, useState } from "react";
import type { RiskStatus } from "./types";

export type RiskAction = { status: RiskStatus; assignee: string; dueDate: string; issueCreated: boolean; updatedAt: string };
export type RiskActionMap = Record<string, RiskAction>;
const STORAGE_KEY = "xray-risk-actions-v1";
export const EMPTY_ACTION: RiskAction = { status: "open", assignee: "Unassigned", dueDate: "", issueCreated: false, updatedAt: "" };

export function useRiskActions() {
  const [actions, setActions] = useState<RiskActionMap>(() => {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}"); } catch { return {}; }
  });
  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(actions)); }, [actions]);
  const updateAction = (riskId: string, patch: Partial<RiskAction>) => setActions((current) => ({
    ...current, [riskId]: { ...EMPTY_ACTION, ...current[riskId], ...patch, updatedAt: new Date().toISOString() }
  }));
  return { actions, updateAction };
}
