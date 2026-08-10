import { memo } from "react";
import { Handle, Position, useStore, type NodeProps, type ReactFlowState } from "reactflow";
import { NODE_COLORS, TIER_BORDER_STYLE } from "./node-visuals";
import { NODE_TYPE_LABELS, type AttackGraphNode } from "./types";

interface GraphNodeData extends AttackGraphNode {
  dimmed?: boolean;
  highlighted?: boolean;
  onPrimaryPath?: boolean;
  direction?: "TB" | "LR";
}

// Real viewport zoom, read via React Flow's own store — the documented
// way to build zoom-aware ("semantic zoom") custom nodes. This does NOT
// resize the node itself (its 220x56 footprint in flow-space, and every
// font-size below, are fixed and identical at every zoom level); it only
// changes which content is rendered inside that fixed footprint. At very
// low zoom, text would be illegible regardless of font-size choice, so
// we swap to a simplified non-text representation rather than shrinking
// text toward unreadability.
const zoomSelector = (s: ReactFlowState) => s.transform[2];

function GraphNodeInner({ data, selected }: NodeProps<GraphNodeData>) {
  const zoom = useStore(zoomSelector);
  const colors = NODE_COLORS[data.type];
  const border = TIER_BORDER_STYLE[data.tier];

  // Emphasis hierarchy, strongest to weakest: selected > highlighted
  // (part of the active path/neighbor set) > on the primary path by
  // default > dimmed (present but not currently relevant) > plain.
  let ringWidth = 0;
  let ringColor = colors.border;
  if (selected) {
    ringWidth = 3;
  } else if (data.highlighted) {
    ringWidth = 2;
    ringColor = "#4DD8E8";
  }

  const containerStyle = {
    width: 220,
    height: 72,
    background: colors.bg,
    borderColor: colors.border,
    borderWidth: border.width,
    borderStyle: border.dasharray === "0" ? ("solid" as const) : ("dashed" as const),
    opacity: data.dimmed ? 0.18 : data.onPrimaryPath === false ? 0.8 : border.opacity,
    boxShadow: ringWidth ? `0 0 0 ${ringWidth}px ${ringColor}` : "none",
  };

  // Below this, two lines of 9-12px text would render at a fraction of a
  // pixel tall — genuinely illegible no matter the font-size. Rather
  // than let that happen, show only a colored identity marker; the type
  // color alone still communicates structure at a glance from far out.
  if (zoom < 0.35) {
    return (
      <div style={containerStyle} className="flex items-center justify-center overflow-hidden rounded-lg transition-all">
        <Handle type="target" position={data.direction === "LR" ? Position.Left : Position.Top} style={{ opacity: 0 }} />
        <div className="h-2.5 w-2.5 rounded-full" style={{ background: colors.border }} />
        <Handle type="source" position={data.direction === "LR" ? Position.Right : Position.Bottom} style={{ opacity: 0 }} />
      </div>
    );
  }

  // Normal zoom: exactly what shipped before — type + title, unchanged
  // font sizes. Above ~1x zoom, there's room to add one more identifying
  // line without crowding the fixed-size node.
  const showExtraDetail = zoom >= 1.0;
  const extraDetail = data.timestamp
    ? new Date(data.timestamp).toLocaleTimeString()
    : typeof data.data?.severity === "string"
      ? `Severity: ${data.data.severity}`
      : null;

  return (
    <div style={containerStyle} className="flex flex-col justify-center overflow-hidden rounded-lg px-3 py-1.5 text-xs transition-all">
      <Handle type="target" position={data.direction === "LR" ? Position.Left : Position.Top} style={{ opacity: 0 }} />
      <div className="mb-0.5 truncate text-[9px] uppercase tracking-wide" style={{ color: colors.text }}>
        {NODE_TYPE_LABELS[data.type]}
      </div>
      <div className="line-clamp-2 leading-tight text-text-primary" title={data.label}>
        {data.label}
      </div>
      {showExtraDetail && extraDetail && (
        <div className="mt-0.5 truncate text-[9px] text-text-muted">{extraDetail}</div>
      )}
      <Handle type="source" position={data.direction === "LR" ? Position.Right : Position.Bottom} style={{ opacity: 0 }} />
    </div>
  );
}

export const GraphNode = memo(GraphNodeInner);
