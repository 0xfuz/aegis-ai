export type NodeType =
  | "incident"
  | "event"
  | "evidence"
  | "ioc"
  | "account"
  | "asset"
  | "ip_domain"
  | "attack_phase"
  | "mitre_technique"
  | "finding"
  | "hypothesis"
  | "uncertainty";

export type EdgeType =
  | "caused_by"
  | "related_to"
  | "observed_in"
  | "originated_from"
  | "targeted"
  | "associated_with"
  | "supports"
  | "contradicts"
  | "leads_to";

export type ConfidenceTier = "confirmed" | "probable" | "possible" | "unknown";

export interface AttackGraphNode {
  id: string;
  type: NodeType;
  label: string;
  tier: ConfidenceTier;
  timestamp: string | null;
  data: Record<string, unknown>;
}

export interface AttackGraphEdge {
  id: string;
  source: string;
  target: string;
  relationship: EdgeType;
  tier: ConfidenceTier;
  rationale: string;
}

export interface AttackGraphData {
  investigation_id: string;
  nodes: AttackGraphNode[];
  edges: AttackGraphEdge[];
}

/** Presentation-only layout choices.  These never alter canonical graph data. */
export type GraphLayoutMode = "hierarchical" | "left-right" | "top-bottom";

export const NODE_TYPE_LABELS: Record<NodeType, string> = {
  incident: "Incident",
  event: "Event",
  evidence: "Evidence",
  ioc: "IOC",
  account: "Account",
  asset: "Asset",
  ip_domain: "IP / Domain",
  attack_phase: "Attack phase",
  mitre_technique: "MITRE technique",
  finding: "Finding",
  hypothesis: "Hypothesis",
  uncertainty: "Uncertainty",
};

export const TIER_LABELS: Record<ConfidenceTier, string> = {
  confirmed: "Confirmed",
  probable: "Probable",
  possible: "Possible",
  unknown: "Unknown / insufficient evidence",
};
