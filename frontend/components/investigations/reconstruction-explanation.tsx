import Link from "next/link";
import { Card } from "@/components/ui/card";
import type { InvestigationReconstruction, ReconstructionActivity, ReconstructionGap } from "@/lib/reconstruction-client";

function StatusBadge({ label, tone = "neutral" }: { label: string; tone?: "neutral" | "warning" | "blocking" | "info" }) {
  const styles = { neutral: "border-hairline text-text-muted", warning: "border-severity-medium/40 text-severity-medium", blocking: "border-severity-critical/40 text-severity-critical", info: "border-signal/40 text-signal" };
  return <span className={`inline-flex rounded border px-1.5 py-0.5 text-[11px] font-medium ${styles[tone]}`}>{label}</span>;
}

export function UncertaintyBadge({ code }: { code: string }) {
  return <span aria-label={`Uncertainty: ${code}`} className="inline-flex rounded border border-severity-medium/40 px-1.5 py-0.5 text-[11px] text-severity-medium">Uncertainty: {code}</span>;
}

const workspaceLinks = [
  ["Evidence", "evidence"], ["Timeline", "timeline"], ["Entities", "entities"], ["Indicators", "indicators"],
  ["Attack Graph", "relationships"], ["Findings", "findings"], ["MITRE ATT&CK", "mitre"],
] as const;

function warningCodes(data: InvestigationReconstruction) {
  return data.context.warnings.flatMap((warning) => warning.code ? [warning.code] : []);
}

export function ReconstructionOverview({ investigationId, data }: { investigationId: string; data: InvestigationReconstruction }) {
  const codes = warningCodes(data);
  const hasPromotionWarning = codes.some((code) => code.startsWith("PROMOTION_") || code.startsWith("CORRELATION_") || code === "TRIAGE_LINK_MISSING");
  const correlationMembers = data.context.section_counts.correlation_v2 ?? 0;
  const mode = correlationMembers > 0 && !hasPromotionWarning ? "Promoted correlation-v2 context" : hasPromotionWarning ? "Degraded reconstruction" : "Evidence-only reconstruction";
  const omissionCount = data.context.omissions.length + data.pagination.total_omitted + data.activity.omitted + data.gaps.omitted;
  return <section aria-labelledby="reconstruction-overview"><h2 id="reconstruction-overview" className="mb-2 text-base font-medium">Certified reconstruction overview</h2><Card>
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-sm font-medium">{data.investigation.title}</h3><p className="mt-1 text-xs text-text-muted">Investigation status: {data.investigation.status}</p></div><StatusBadge label={mode} tone={hasPromotionWarning ? "warning" : correlationMembers > 0 ? "info" : "neutral"} /></div>
    <dl className="mt-4 grid gap-3 text-xs md:grid-cols-3"><div><dt className="text-text-muted">Reconstruction policy</dt><dd>{data.policy_id}</dd></div><div><dt className="text-text-muted">Context / activity</dt><dd>{data.versions.context} / {data.versions.activity}</dd></div><div><dt className="text-text-muted">Gap policy</dt><dd>{data.versions.gaps}</dd></div></dl>
    <div className="mt-4"><h3 className="text-xs font-medium text-text-muted">Bounded factual sections</h3><ul aria-label="Bounded factual section counts" className="mt-2 flex flex-wrap gap-2">{Object.entries(data.context.section_counts).map(([section, count]) => <li key={section}><StatusBadge label={`${section.replaceAll("_", " ")}: ${count}`} /></li>)}</ul></div>
    <p className="mt-4 text-xs text-text-muted">{data.context.warnings.length + data.warnings.length} warnings and {omissionCount} omitted items are reported by the server. Omitted data is not treated as absent.</p>
    {codes.length > 0 && <ul aria-label="Reconstruction warnings" className="mt-2 flex flex-wrap gap-2">{codes.map((code) => <li key={code}><UncertaintyBadge code={code} /></li>)}</ul>}
    {data.warnings.length > 0 && <ul aria-label="Server reconstruction warnings" className="mt-2 flex flex-wrap gap-2">{data.warnings.map((warning, index) => <li key={`${warning.section}-${warning.reason}-${index}`}><StatusBadge label={`${warning.section}: ${warning.reason} (${warning.omitted})`} tone="warning" /></li>)}</ul>}
    {data.context.omissions.length > 0 && <ul aria-label="Context omissions" className="mt-2 flex flex-wrap gap-2">{data.context.omissions.map((omission, index) => <li key={`${omission.section}-${omission.reason}-${index}`}><StatusBadge label={`${omission.reason}: ${omission.section} (${omission.returned_count}/${omission.original_count})`} tone="info" /></li>)}</ul>}
    <nav aria-label="Open factual investigation workspaces" className="mt-4 flex flex-wrap gap-2">{workspaceLinks.map(([label, segment]) => <Link key={segment} className="rounded border border-hairline px-2 py-1 text-xs text-signal hover:bg-surface-raised" href={`/investigations/${investigationId}/${segment}`}>{label}</Link>)}</nav>
  </Card></section>;
}

function timestamp(value: string | null) { return value ?? "Not supplied"; }
function activityDescription(activity: ReconstructionActivity) {
  if (activity.position === "OUTSIDE") return "Outside the server-defined activity window.";
  if (activity.position === "UNKNOWN") return "Time position is unavailable.";
  return `Server-relative position: ${activity.position}.`;
}

export function ActivityWindowPanel({ data }: { data: InvestigationReconstruction }) {
  const { activity } = data;
  const anchor = activity.anchor;
  return <section aria-labelledby="activity-window" className="mt-5"><h2 id="activity-window" className="mb-2 text-base font-medium">Activity window</h2><Card>
    {!anchor ? <p className="text-sm text-text-muted">No temporal anchor is available. This is unavailable observation, not evidence that activity did not occur.</p> : <><h3 className="text-sm font-medium">{anchor.start === anchor.end ? "Anchor point" : "Anchor interval"}</h3><p className="mt-1 break-all font-mono text-xs text-text-muted">{anchor.start}{anchor.start === anchor.end ? "" : ` → ${anchor.end}`} UTC</p><p className="mt-2 text-xs text-text-muted">Before/after expansion bounds are not exposed by the certified response. Relative positions below are server-authored and are not recalculated in the browser.</p></>}
    {activity.warnings.length > 0 && <ul aria-label="Activity availability warnings" className="mt-3 flex flex-wrap gap-2">{activity.warnings.map((warning) => <li key={warning}><UncertaintyBadge code={warning} /></li>)}</ul>}
    <p className="mt-3 text-xs text-text-muted">{activity.omitted} activities omitted by the server policy.</p>
    {activity.activities.length === 0 ? <p className="mt-4 text-sm text-text-muted">No bounded activities are available for this reconstruction.</p> : <ol aria-label="Server-ordered reconstruction activities" className="mt-4 space-y-3">{activity.activities.map((item) => <li key={`${item.type}-${item.id}`} className="rounded border border-hairline p-3 text-xs"><div className="flex flex-wrap items-center gap-2"><StatusBadge label={item.type} /><StatusBadge label={item.position} tone={item.position === "OUTSIDE" || item.position === "UNKNOWN" ? "warning" : "neutral"} /></div><p className="mt-2">Activity reference: {item.id}</p><p className="mt-2">{activityDescription(item)}</p><dl className="mt-2 grid gap-2 sm:grid-cols-2"><div><dt className="text-text-muted">Original UTC</dt><dd className="break-all font-mono">{timestamp(item.original_timestamp)}</dd></div><div><dt className="text-text-muted">Effective UTC / basis</dt><dd className="break-all font-mono">{timestamp(item.effective_timestamp)} · {item.time_basis}</dd></div></dl>{item.uncertainty.length > 0 && <ul aria-label={`Uncertainties for ${item.type} ${item.id}`} className="mt-2 flex flex-wrap gap-1">{item.uncertainty.map((code) => <li key={code}><UncertaintyBadge code={code} /></li>)}</ul>}</li>)}</ol>}
  </Card></section>;
}

function gapTone(gap: ReconstructionGap) { return gap.severity === "BLOCKING" ? "blocking" : gap.severity === "WARNING" ? "warning" : "info" as const; }

export function ReconstructionGapPanel({ data }: { data: InvestigationReconstruction }) {
  const { gaps } = data;
  return <section aria-labelledby="reconstruction-gaps" className="mt-5"><h2 id="reconstruction-gaps" className="mb-2 text-base font-medium">Completeness and uncertainty</h2><Card>
    <p className="text-xs text-text-muted">Gaps describe reconstruction limits. They are not Facts, Findings, claims, or MITRE conclusions.</p>
    <p className="mt-2 text-xs text-text-muted">{gaps.omitted} gap records omitted by the server policy.</p>
    {gaps.gaps.length === 0 ? <p className="mt-4 text-sm text-text-muted">No bounded reconstruction gaps are reported.</p> : <ul aria-label="Reconstruction gaps" className="mt-4 space-y-3">{gaps.gaps.map((gap, index) => <li key={`${gap.code}-${gap.target_id ?? index}`} className="rounded border border-hairline p-3 text-xs"><div className="flex flex-wrap gap-2"><StatusBadge label={gap.severity} tone={gapTone(gap)} /><StatusBadge label={gap.classification} /><StatusBadge label={gap.code} /></div><p className="mt-2">Section: {gap.section}</p>{gap.detail && <p className="mt-1 text-text-muted">{gap.detail}</p>}{gap.target_type && <p className="mt-1 text-text-muted">Target: {gap.target_type}{gap.target_id ? ` · ${gap.target_id}` : ""}</p>}{gap.provenance.length > 0 && <p className="mt-2 text-text-muted">Provenance references: {gap.provenance.join(", ")}. {gap.classification === "CONTRADICTORY" ? "Both references are retained; no winner is selected." : ""}</p>}</li>)}</ul>}
  </Card></section>;
}

export function ReconstructionExplanation({ investigationId, data }: { investigationId: string; data: InvestigationReconstruction }) {
  return <div className="mb-5"><ReconstructionOverview investigationId={investigationId} data={data} /><ActivityWindowPanel data={data} /><ReconstructionGapPanel data={data} /></div>;
}
