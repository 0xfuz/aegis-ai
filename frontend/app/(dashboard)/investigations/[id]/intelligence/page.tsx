"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { WorkspaceNav } from "@/components/investigations/workspace-nav";
import { useInvestigationReconstruction } from "@/lib/use-investigation-reconstruction";
import { ReconstructionExplanation } from "@/components/investigations/reconstruction-explanation";
import { CitationList, ClaimExplanationPanel, PromotionExplanationPanel, type IntelligenceAnalysisRead } from "@/components/investigations/claim-citation-explanation";

type Analysis = IntelligenceAnalysisRead;
const tabs = ["SUMMARY", "OBSERVATION", "HYPOTHESIS", "RECOMMENDATION", "QUESTION", "REASONING"];

export default function IntelligencePage() {
  const { id } = useParams<{ id: string }>();
  const { user, hasPermission } = useAuth();
  const [data, setData] = useState<Analysis | null>(null);
  const [tab, setTab] = useState("SUMMARY");
  const [error, setError] = useState<string | null>(null);
  const reconstruction = useInvestigationReconstruction(id);
  const load = useCallback(async () => {
    try { setData(await apiFetch<Analysis>(`/api/v1/investigations/${id}/intelligence`)); }
    catch (err) { setError(err instanceof ApiError ? err.message : "No intelligence analysis yet."); }
  }, [id]);
  useEffect(() => { void load(); }, [load]);
  async function run() { setError(null); try { await apiFetch(`/api/v1/investigations/${id}/intelligence`, { method: "POST" }); await load(); } catch (err) { setError(err instanceof ApiError ? err.message : "Unable to run intelligence analysis."); } }
  async function convert(itemId: string) { try { await apiFetch(`/api/v1/investigations/intelligence/items/${itemId}/finding`, { method: "POST", body: JSON.stringify({}) }); await load(); } catch (err) { setError(err instanceof ApiError ? err.message : "Unable to convert this intelligence item."); } }
  const items = data?.items.filter((item) => item.kind === tab) ?? [];
  return <><div className="mb-2 text-xs text-text-muted"><Link href="/investigations">Cases</Link> / Investigation Intelligence</div><h1 className="font-display text-lg">Investigation Intelligence</h1><WorkspaceNav investigationId={id} />
    {reconstruction.status === "loading" && <p aria-live="polite" className="mb-3 text-xs text-text-muted">Loading certified reconstruction…</p>}
    {reconstruction.status === "ready" && <><ReconstructionExplanation investigationId={id} data={reconstruction.data} /><PromotionExplanationPanel data={reconstruction.data} /><CitationList data={reconstruction.data} /></>}
    {["forbidden", "not_found", "invalid"].includes(reconstruction.status) && <Card className="mb-3" role="alert"><p className="text-sm text-text-muted">{reconstruction.error}</p></Card>}
    {reconstruction.status === "error" && <Card className="mb-3" role="alert"><p className="text-sm text-text-muted">{reconstruction.error}</p><Button variant="secondary" className="mt-2" onClick={reconstruction.retry}>Retry reconstruction</Button></Card>}
    <ClaimExplanationPanel analysis={data} loadError={error} citations={reconstruction.status === "ready" ? reconstruction.data.sections.citations : []} canReview={Boolean(user?.is_active && hasPermission("investigation:write"))} onReviewed={load} />
    <div className="mb-3 mt-5 flex gap-2"><Button onClick={run}>Run analysis</Button><span className="self-center text-xs text-text-muted">AI INFERENCE · reviewable, never FACT.</span></div>{error ? <Card><p className="text-sm text-text-muted">{error}</p></Card> : !data ? <p className="text-sm text-text-muted">Loading intelligence notebook…</p> : <><div className="mb-3 flex flex-wrap gap-1">{tabs.map((name) => <button key={name} onClick={() => setTab(name)} className="rounded px-2 py-1 text-xs text-text-muted hover:bg-surface-raised">{name[0] + name.slice(1).toLowerCase()}</button>)}</div><Card>{items.length ? items.map((item) => <div key={item.id} className="border-b border-hairline py-3 last:border-0"><div className="flex justify-between text-xs"><span>{item.review_status} · {item.confidence ?? "—"}%</span><span>{item.kind}</span></div><p className="mt-2 text-sm">{item.statement}</p><div className="mt-2 text-xs text-text-muted">Supporting facts: {item.fact_links.map((link) => <Link className="mr-2 text-signal" key={`${link.role}-${link.fact_id}`} href={`/investigations/${id}/evidence`}>{link.role}: {link.fact_id}</Link>)}</div>{item.review_status === "CONFIRMED" && ["OBSERVATION", "HYPOTHESIS", "RECOMMENDATION"].includes(item.kind) && <Button className="mt-2" onClick={() => void convert(item.id)}>Convert to Finding</Button>}</div>) : <p className="text-sm text-text-muted">No items in this notebook section.</p>}</Card></>}</>;
}
