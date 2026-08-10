import type { ConfidenceTier, NodeType } from "./types";

// Reuses the existing design system tokens (severity ramp, signal,
// cognition) rather than inventing a new palette for the graph — the
// UX spec is explicit that visual identity should stay consistent
// across the whole product.
export const NODE_COLORS: Record<NodeType, { bg: string; border: string; text: string }> = {
  incident: { bg: "#E5484D22", border: "#E5484D", text: "#E5484D" },
  event: { bg: "#4DD8E822", border: "#4DD8E8", text: "#4DD8E8" },
  attack_phase: { bg: "#9B8CFF22", border: "#9B8CFF", text: "#9B8CFF" },
  mitre_technique: { bg: "#9B8CFF22", border: "#9B8CFF", text: "#9B8CFF" },
  hypothesis: { bg: "#F2C94C22", border: "#F2C94C", text: "#F2C94C" },
  evidence: { bg: "#4DD8E822", border: "#4DD8E8", text: "#4DD8E8" },
  ioc: { bg: "#F2994A22", border: "#F2994A", text: "#F2994A" },
  ip_domain: { bg: "#F2994A22", border: "#F2994A", text: "#F2994A" },
  asset: { bg: "#6B728022", border: "#8A93A3", text: "#E8ECF2" },
  account: { bg: "#6B728022", border: "#8A93A3", text: "#E8ECF2" },
  finding: { bg: "#4DD8E822", border: "#4DD8E8", text: "#4DD8E8" },
  uncertainty: { bg: "#6B728022", border: "#6B7280", text: "#8A93A3" },
};

// The confidence tier controls the BORDER STYLE, independent of the
// type color above — this is what lets someone tell "a confirmed IP"
// apart from "a possible IP" at a glance, per the person's explicit
// requirement that confirmed/probable/possible/unknown be visually
// distinguishable.
export const TIER_BORDER_STYLE: Record<ConfidenceTier, { dasharray: string; opacity: number; width: number }> = {
  confirmed: { dasharray: "0", opacity: 1, width: 2 },
  probable: { dasharray: "0", opacity: 0.85, width: 1.5 },
  possible: { dasharray: "5,3", opacity: 0.7, width: 1.5 },
  unknown: { dasharray: "2,3", opacity: 0.55, width: 1 },
};
