import type { EvidenceSummary, LensEnvelope } from "../api";

export type ProductView = "overview" | "risks" | "ask" | "graph" | "imports" | "actions" | "settings";
export type RiskKind = "key-person" | "coordination" | "missing-evidence";
export type RiskPriority = "P1" | "P2" | "P3" | "P4";
export type RiskStatus = "open" | "acknowledged" | "mitigating" | "resolved" | "dismissed";

export type RiskItem = {
  id: string; priority: RiskPriority; kind: RiskKind; title: string; affectedArea: string; team: string;
  confidence: number; dataCoverage: number; lastObserved: string; evidence: EvidenceSummary[];
  source: LensEnvelope<unknown>["source"]; sourceLabel: string; sourceKey?: string; targetKey?: string;
  explanation: string; impact: string; recommendation: string; limitations: string[];
  query: LensEnvelope<unknown>["executed_query"];
};

export type RiskFilters = { kind: RiskKind | "all"; confidence: "all" | "high" | "medium" | "low"; team: string; windowDays: number };
