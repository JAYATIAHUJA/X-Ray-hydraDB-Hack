import type { FaultlineFinding, GapFinding, GhostFinding, LensEnvelope } from "../api";
import type { RiskItem, RiskPriority } from "./types";

const suffix = (value: string) => value.split(":").at(-1)?.replaceAll("-", " ") ?? value;
const titleCase = (value: string) => value.replace(/\b\w/g, (letter) => letter.toUpperCase());
function priority(score: number): RiskPriority { return score >= 80 ? "P1" : score >= 60 ? "P2" : score >= 35 ? "P3" : "P4"; }
function sourceContext<T>(envelope?: LensEnvelope<T>) { return { limitations: envelope?.limitations ?? [], query: envelope?.executed_query ?? null, source: envelope?.source ?? "fixture" as const }; }

export function buildRiskInbox(ghosts?: LensEnvelope<GhostFinding>, faultlines?: LensEnvelope<FaultlineFinding>, gaps?: LensEnvelope<GapFinding>): RiskItem[] {
  const coordination: RiskItem[] = (faultlines?.findings ?? []).map((finding, index) => {
    const sourceModule = titleCase(suffix(finding.source_module_key));
    const targetModule = titleCase(suffix(finding.target_module_key));
    const sourceOwner = titleCase(suffix(finding.source_owner_key));
    const targetOwner = titleCase(suffix(finding.target_owner_key));
    const confidence = Math.max(35, Math.min(95, Math.round(Math.min(finding.source_owner_confidence ?? 85, finding.target_owner_confidence ?? 85))));
    return {
      id: `coordination-${index}-${finding.source_module_key}-${finding.target_module_key}`,
      priority: priority(Math.min(100, finding.severity * 8)), kind: "coordination",
      title: `${sourceModule} depends on ${targetModule}, but the owners have no observed coordination path.`,
      affectedArea: `${sourceModule} → ${targetModule}`, team: sourceModule, confidence,
      dataCoverage: Math.max(45, Math.min(96, confidence - 8)), lastObserved: finding.communication_distance === null ? "No path observed" : `${finding.communication_distance} hops`,
      evidence: finding.evidence, sourceLabel: "Faultline analysis", sourceKey: finding.source_owner_key, targetKey: finding.target_owner_key,
      explanation: `${sourceModule} has a technical dependency on ${targetModule}, while the available communication graph does not show a sufficiently short path between ${sourceOwner} and ${targetOwner}.`,
      impact: `A change in ${targetModule} can reach ${sourceModule} before both owners have aligned on the change.`,
      recommendation: `Schedule a dependency review between ${sourceOwner} and ${targetOwner}, then record the agreed interface and owner.`, ...sourceContext(faultlines)
    };
  });
  const keyPeople: RiskItem[] = (ghosts?.findings ?? []).map((finding, index) => ({
    id: `key-person-${index}-${finding.person_key}`, priority: priority(Math.min(100, 50 + Math.max(0, finding.rank_gap) * 5)), kind: "key-person",
    title: `Key-person dependency on ${finding.display_name} for coordination continuity.`, affectedArea: "Cross-team coordination", team: "Organization",
    confidence: Math.max(40, Math.min(96, Math.round(55 + finding.sampled_centrality * 100))), dataCoverage: 82, lastObserved: `${finding.communication_degree} direct contacts`,
    evidence: finding.evidence, sourceLabel: "Ghost analysis", sourceKey: finding.person_key,
    explanation: `${finding.display_name} ranks #${finding.structural_rank} in the observed coordination graph but #${finding.formal_rank} by formal role. This is a risk indicator, not an employee performance score.`,
    impact: finding.removal_impact ? `${finding.removal_impact.pairs_lost_without_person} of ${finding.removal_impact.reachable_pairs_before} sampled coordination paths disappear in the removal test.` : "Coordination paths may be more concentrated than the formal organization suggests.",
    recommendation: "Pair this person with a second owner, document recurring decisions, and repeat the analysis after the handoff.", ...sourceContext(ghosts)
  }));
  const missingEvidence: RiskItem[] = (gaps?.findings ?? []).map((finding, index) => {
    const item = titleCase(suffix(finding.phantom_key)); const inWindow = finding.window_position === "in_window";
    return {
      id: `missing-${index}-${finding.phantom_key}`, priority: inWindow || finding.reason === "required_sequence_step_missing" ? "P2" : "P3", kind: "missing-evidence",
      title: `Missing decision evidence: ${item}.`, affectedArea: titleCase(suffix(finding.successor_keys[0] ?? finding.predecessor_keys[0] ?? "Unknown workflow")), team: "Unassigned",
      confidence: inWindow ? 78 : 58, dataCoverage: inWindow ? 74 : 51, lastObserved: inWindow ? "Inside export window" : "Export boundary", evidence: finding.evidence,
      sourceLabel: "Gap analysis", sourceKey: finding.predecessor_keys[0], targetKey: finding.successor_keys[0],
      explanation: `The configured workflow or reply chain requires ${item}, but that record is not present in the available corpus.`,
      impact: "The team cannot verify the complete decision or approval chain from the supplied evidence.",
      recommendation: "Request the missing record or confirm that the export boundary explains its absence before treating this as a process failure.", ...sourceContext(gaps)
    };
  });
  const order: Record<RiskPriority, number> = { P1: 1, P2: 2, P3: 3, P4: 4 };
  return [...coordination, ...keyPeople, ...missingEvidence].sort((a, b) => order[a.priority] - order[b.priority] || b.confidence - a.confidence);
}

export function riskKindLabel(kind: RiskItem["kind"]) { return kind === "coordination" ? "Uncoordinated dependency" : kind === "key-person" ? "Key-person dependency" : "Missing decision evidence"; }
