import { Card } from "@/components/ui/card";
import type { InvestigationReconstruction, ReconstructionCitation, ReconstructionJson } from "@/lib/reconstruction-client";

export type IntelligenceClaim = {
  id: string;
  kind: string;
  claim_type: "FACT" | "OBSERVATION" | "INFERENCE" | "HYPOTHESIS" | "RECOMMENDATION";
  origin: "SOURCE" | "DETERMINISTIC_ENGINE" | "AI" | "ANALYST";
  statement: string;
  confidence: number | null;
  review_status: "PENDING" | "CONFIRMED" | "REJECTED" | "UNRESOLVED" | "SUPERSEDED";
  fact_links: { fact_id: string; role: string }[];
};

export type IntelligenceAnalysisRead = { status: string; generated_at: string | null; items: IntelligenceClaim[] };

const roles = {
  SUPPORTS: "Evidence consistent with this claim.",
  CONTRADICTS: "Evidence in tension with this claim.",
  CONTEXT: "Relevant context; not proof of the claim.",
} as const;

function json(value: ReconstructionJson) {
  return JSON.stringify(value);
}

function claimSemantics(claim: IntelligenceClaim) {
  if (claim.claim_type === "FACT") return "FACT: deterministic origin required.";
  if (claim.origin === "AI" && claim.claim_type === "OBSERVATION") return "Reviewable AI output.";
  if (claim.claim_type === "INFERENCE" || claim.claim_type === "HYPOTHESIS") return "Not established fact.";
  if (claim.claim_type === "RECOMMENDATION") return "Advisory only — no action executed.";
  return "Claim type and origin remain distinct from its analyst review status.";
}

function CitationLinks({ citation }: { citation: ReconstructionCitation }) {
  if (citation.claim_links.length === 0) return <p className="mt-2 text-xs text-text-muted">Unlinked citation — no scoped intelligence claim link is available.</p>;
  return <ul aria-label={`Claim links for citation ${citation.alias}`} className="mt-2 space-y-1 text-xs">
    {citation.claim_links.map((link, index) => <li key={`${link.claim_id}-${link.role}-${index}`}><button className="rounded text-left text-signal underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal" onClick={() => document.getElementById(`claim-${link.claim_id}`)?.focus()}>Claim {link.claim_id}</button><span> · {link.role} — {roles[link.role]}</span></li>)}
  </ul>;
}

export function CitationList({ data }: { data: InvestigationReconstruction }) {
  const citations = data.sections.citations;
  return <section aria-labelledby="typed-citations" className="mt-5"><h2 id="typed-citations" className="mb-2 text-base font-medium">Typed citations</h2><Card>
    <p className="text-xs text-text-muted">Immutable typed references. Citation roles describe relationship to a claim; they do not establish facts.</p>
    {citations.length === 0 ? <p className="mt-4 text-sm text-text-muted">No bounded typed citations are available.</p> : <ol aria-label="Server-ordered typed citations" className="mt-4 space-y-3">{citations.map((citation) => <li key={citation.id} className="rounded border border-hairline p-3"><div className="flex flex-wrap gap-2 text-xs"><span className="font-medium">{citation.alias}</span><span>{citation.type}</span></div>{["FINDING", "MITRE_MAPPING"].includes(citation.type) && <p className="mt-1 text-xs text-text-muted">Finding/MITRE citation: CONTEXT-only.</p>}<dl className="mt-2 grid gap-2 text-xs sm:grid-cols-2"><div><dt className="text-text-muted">Context / builder / policy</dt><dd>{citation.context_version} / {citation.builder_version} / {citation.policy_version}</dd></div>{citation.producer && <div><dt className="text-text-muted">Producer</dt><dd>{citation.producer}{citation.producer_version ? ` / ${citation.producer_version}` : ""}</dd></div>}<div><dt className="text-text-muted">Safe locator</dt><dd className="break-all font-mono">{json(citation.locator)}</dd></div></dl><CitationLinks citation={citation} />{citation.claim_links_omitted > 0 && <p className="mt-2 text-xs text-text-muted">{citation.claim_links_omitted} claim links omitted by the server bound.</p>}</li>)}</ol>}
  </Card></section>;
}

function ClaimCitations({ claimId, citations }: { claimId: string; citations: ReconstructionCitation[] }) {
  const linked = citations.flatMap((citation) => citation.claim_links.filter((link) => link.claim_id === claimId).map((link) => ({ alias: citation.alias, type: citation.type, role: link.role })));
  if (linked.length === 0) return <p className="mt-2 text-xs text-text-muted">No bounded typed citations are linked to this claim.</p>;
  return <div className="mt-2 text-xs"><p className="text-text-muted">Linked typed citations (server order):</p>{(["SUPPORTS", "CONTRADICTS", "CONTEXT"] as const).map((role) => {
    const group = linked.filter((link) => link.role === role);
    return group.length > 0 ? <p key={role} className="mt-1">{role}: {group.map((link) => `${link.alias} (${link.type})`).join(", ")} — {roles[role]}</p> : null;
  })}</div>;
}

export function ClaimExplanationPanel({ analysis, loadError, citations = [] }: { analysis: IntelligenceAnalysisRead | null; loadError: string | null; citations?: ReconstructionCitation[] }) {
  if (!analysis) return <section aria-labelledby="intelligence-claims" className="mt-5"><h2 id="intelligence-claims" className="mb-2 text-base font-medium">Analyst-reviewed claims</h2><Card><p className="text-sm text-text-muted">{loadError ?? "Loading intelligence claim status…"}</p></Card></section>;
  const degraded = ["FAILED", "CANCELLED"].includes(analysis.status);
  return <section aria-labelledby="intelligence-claims" className="mt-5"><h2 id="intelligence-claims" className="mb-2 text-base font-medium">Analyst-reviewed claims</h2><Card>
    {degraded && <p role="status" className="text-sm text-text-muted">Intelligence run {analysis.status.toLowerCase()}. Deterministic reconstruction remains available; no claim is fabricated.</p>}
    {!degraded && analysis.items.length === 0 && <p className="text-sm text-text-muted">No intelligence claims generated yet.</p>}
    {analysis.items.length > 0 && <ol aria-label="Server-ordered intelligence claims" className="space-y-3">{analysis.items.map((claim) => <li key={claim.id} id={`claim-${claim.id}`} tabIndex={-1} className="rounded border border-hairline p-3 focus:outline focus:outline-2 focus:outline-signal"><div className="flex flex-wrap gap-2 text-xs"><span className="font-medium">{claim.claim_type}</span><span>Origin: {claim.origin}</span><span>Review: {claim.review_status}</span>{claim.confidence !== null && <span>Confidence: {claim.confidence}%</span>}</div><p className="mt-2 text-sm">{claim.statement}</p><p className="mt-2 text-xs text-text-muted">{claimSemantics(claim)} {claim.review_status === "CONFIRMED" ? "CONFIRMED is an analyst-reviewed claim status; it does not change claim type or origin." : ""}</p><ClaimCitations claimId={claim.id} citations={citations} /></li>)}</ol>}
  </Card></section>;
}

export function PromotionExplanationPanel({ data }: { data: InvestigationReconstruction }) {
  const projection = data.promotion;
  return <section aria-labelledby="promotion-explanation" className="mt-5"><h2 id="promotion-explanation" className="mb-2 text-base font-medium">Promotion, correlation and triage</h2><Card>
    <p className="text-xs text-text-muted">Persisted promotion, correlation, and triage records only. Nothing is recalculated in the browser.</p>
    <p className="mt-2 text-sm">State: {projection.state}{projection.warning ? ` · ${projection.warning}` : ""}</p>
    {!projection.promotion ? <p className="mt-3 text-sm text-text-muted">No analyst promotion is available for this reconstruction.</p> : <><dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2"><div><dt className="text-text-muted">Promotion</dt><dd>{projection.promotion.status} · {projection.promotion.promoted_at}</dd></div><div><dt className="text-text-muted">Promoted cluster</dt><dd>{projection.promotion.cluster_id}</dd></div>{projection.correlation && <><div><dt className="text-text-muted">Correlation version</dt><dd>{projection.correlation.version}</dd></div><div><dt className="text-text-muted">Membership count</dt><dd>{projection.correlation.membership_count}</dd></div></>}{projection.triage && <><div><dt className="text-text-muted">Triage priority / score</dt><dd>{projection.triage.priority} / {projection.triage.score}</dd></div><div><dt className="text-text-muted">Triage version</dt><dd>{projection.triage.version}</dd></div></>}</dl>{projection.correlation && <><p className="mt-3 text-xs text-text-muted">{projection.correlation.memberships_omitted} membership summaries omitted by the server bound.</p>{projection.correlation.memberships.length > 0 && <ol aria-label="Server-ordered correlation memberships" className="mt-2 space-y-2">{projection.correlation.memberships.map((membership) => <li key={membership.id} className="rounded border border-hairline p-2 text-xs">Score: {membership.score}<span className="ml-2">Added: {membership.added_at}</span><pre className="mt-1 whitespace-pre-wrap break-all font-sans text-text-muted">{json(membership.reasons)}</pre></li>)}</ol>}</>}</>}
  </Card></section>;
}
