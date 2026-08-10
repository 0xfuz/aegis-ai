"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { WorkspaceNav } from "@/components/investigations/workspace-nav";

type Mapping = { id: string; technique_id: string; technique_name: string | null; tactic: string | null; confidence: number | null; ai_rationale: string; status: string; source_intelligence_item_id: string | null; finding_id: string | null; fact_links: { fact_id: string; role: string }[] };

export default function MitrePage() {
  const { id } = useParams<{ id: string }>();
  const [rows, setRows] = useState<Mapping[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { setRows(await apiFetch<Mapping[]>(`/api/v1/investigations/${id}/mitre-mappings`)); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Unable to load MITRE mappings."); }
  }, [id]);
  useEffect(() => { void load(); }, [load]);
  async function review(mapping: string, status: string) {
    const rationale = status === "REJECTED" ? window.prompt("Rejection rationale (required):") ?? "" : "Confirmed by analyst";
    if (status === "REJECTED" && !rationale.trim()) return;
    await apiFetch(`/api/v1/investigations/mitre-mappings/${mapping}/review`, { method: "POST", body: JSON.stringify({ status, rationale }) });
    await load();
  }
  return <><h1 className="font-display text-lg">MITRE ATT&amp;CK <span className="text-xs font-normal text-cognition">ANALYST REVIEW</span></h1><WorkspaceNav investigationId={id} />{error ? <Card>{error}</Card> : !rows ? <p className="text-sm text-text-muted">Loading MITRE review…</p> : ["CONFIRMED", "PROPOSED", "REJECTED"].map(status => <section key={status} className="mb-5"><h2 className="mb-2 text-sm">{status[0] + status.slice(1).toLowerCase()}</h2>{rows.filter(row => row.status === status).map(row => <Card key={row.id} className="mb-2"><div className="flex justify-between"><b>{row.technique_id} {row.technique_name ?? ""}</b><span className="text-xs text-text-muted">{row.tactic ?? ""} · {row.confidence ?? "—"}%</span></div><p className="mt-2 text-sm">{row.ai_rationale}</p><p className="mt-2 text-xs text-text-muted">Source: {row.finding_id ? `Finding ${row.finding_id}` : row.source_intelligence_item_id ? `AI inference ${row.source_intelligence_item_id}` : "—"}</p><p className="mt-2 text-xs text-text-muted">Supporting FACTs: {row.fact_links.map(link => link.fact_id).join(", ") || "—"}</p>{status === "PROPOSED" && <div className="mt-2 flex gap-3"><button className="text-xs text-signal" onClick={() => void review(row.id, "CONFIRMED")}>Confirm</button><button className="text-xs text-severity-critical" onClick={() => void review(row.id, "REJECTED")}>Reject</button></div>}</Card>)}{rows.filter(row => row.status === status).length === 0 && <Card><p className="text-sm text-text-muted">No {status.toLowerCase()} mappings.</p></Card>}</section>)}</>;
}
