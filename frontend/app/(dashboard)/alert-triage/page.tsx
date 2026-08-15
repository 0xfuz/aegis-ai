"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, apiFetch } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type Triage = { priority: string; score: number; version: string };
type Promotion = { investigation_id: string; status: string };
type Cluster = {
  id: string; correlation_version: string; status: string; member_count: number;
  triage: Triage | null; promotion: Promotion | null;
  promotion_eligible: boolean; promotion_reason: string;
  members?: { id: string; score: number; reasons: unknown[]; added_at: string }[];
};

function safeError(error: unknown, fallback: string): ApiError {
  return error instanceof ApiError ? error : new ApiError(fallback, 500);
}

export default function AlertTriagePage() {
  const router = useRouter();
  const { hasPermission } = useAuth();
  const [rows, setRows] = useState<Cluster[] | null>(null);
  const [selected, setSelected] = useState<Cluster | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);

  const load = () => {
    setRows(null); setSelected(null); setError(null);
    apiFetch<Cluster[]>("/api/v1/alert-triage/clusters")
      .then(setRows).catch((value) => setError(safeError(value, "Couldn't load alert triage.")));
  };
  useEffect(load, []);

  async function showDetail(id: string) {
    setError(null);
    try { setSelected(await apiFetch<Cluster>(`/api/v1/alert-triage/clusters/${encodeURIComponent(id)}`)); }
    catch (value) { setError(safeError(value, "Couldn't load the alert cluster.")); }
  }
  async function promote(id: string) {
    setPending(id); setError(null);
    try {
      const result = await apiFetch<{ investigation_id: string }>(
        `/api/v1/alert-triage/clusters/${encodeURIComponent(id)}/promote`, { method: "POST", body: "{}" },
      );
      router.push(`/investigations/${result.investigation_id}`);
    } catch (value) { setError(safeError(value, "Promotion failed.")); }
    finally { setPending(null); setConfirm(null); }
  }

  return <div>
    <h1 className="font-display text-xl font-medium text-text-primary">Alert triage</h1>
    <p className="mt-1 text-sm text-text-muted">Persisted correlation and triage state. Nothing is recalculated in this view.</p>
    {error && <div role="alert" className="mt-4 rounded border border-severity-critical/40 p-3 text-sm">
      {error.status === 403 ? "You do not have permission to perform this action." : error.status === 404 ? "The requested cluster is unavailable." : error.message}
      <button className="ml-3 underline" onClick={load}>Retry</button>
    </div>}
    {rows === null && !error && <p className="mt-4 text-sm text-text-muted">Loading…</p>}
    {rows?.length === 0 && <Card className="mt-4"><p>No persisted alert clusters are available.</p></Card>}
    <div className="mt-4 space-y-3" aria-label="Alert clusters">
      {rows?.map((cluster) => <Card key={cluster.id}>
        <div className="flex flex-wrap items-center justify-between gap-3"><div>
          <h2 className="font-medium">Cluster {cluster.id}</h2>
          <p className="text-sm text-text-muted">{cluster.correlation_version} · {cluster.member_count} persisted member{cluster.member_count === 1 ? "" : "s"} · {cluster.triage ? `${cluster.triage.priority} / ${cluster.triage.score} (${cluster.triage.version})` : "No persisted triage"}</p>
          <p className="mt-1 text-xs text-text-muted">Status: {cluster.promotion?.status ?? cluster.promotion_reason}</p>
        </div><div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" onClick={() => showDetail(cluster.id)}>View details</Button>
          {cluster.promotion ? <Link className="text-signal underline" href={`/investigations/${cluster.promotion.investigation_id}`}>Open Investigation</Link>
            : hasPermission("investigation:write") && cluster.promotion_eligible ? <div>{confirm === cluster.id ? <div className="flex gap-2">
              <Button onClick={() => promote(cluster.id)} disabled={pending === cluster.id}>{pending === cluster.id ? "Promoting…" : "Confirm promotion"}</Button>
              <Button variant="secondary" onClick={() => setConfirm(null)} disabled={pending === cluster.id}>Cancel</Button>
            </div> : <Button onClick={() => setConfirm(cluster.id)}>Promote to Investigation</Button>}</div> : null}
        </div></div>
      </Card>)}
    </div>
    {selected && <Card className="mt-4" aria-live="polite"><h2 className="font-medium">Cluster detail</h2><p className="text-sm text-text-muted">{selected.members?.length ?? 0} persisted members returned for {selected.correlation_version}.</p></Card>}
  </div>;
}
