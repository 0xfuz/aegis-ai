"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { SeverityBadge } from "@/components/ui/severity-badge";
import { ConfidenceRing } from "@/components/ui/confidence-ring";

interface InvestigationSummary {
  id: string;
  title: string;
  source: string;
  severity: string;
  status: string;
  confidence: number;
  created_at: string;
}
interface DemoScenario { id: string; title: string; loaded: boolean; }

export default function InvestigationsPage() {
  const router = useRouter();
  const [investigations, setInvestigations] = useState<InvestigationSummary[] | null>(null);
  const [demos, setDemos] = useState<DemoScenario[]>([]);
  const [loadingDemo, setLoadingDemo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([apiFetch<InvestigationSummary[]>("/api/v1/investigations"), apiFetch<DemoScenario[]>("/api/v1/demos")])
      .then(([rows, demoRows]) => { setInvestigations(rows); setDemos(demoRows); })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load investigations."));
  }, []);

  async function loadDemo(id: string) {
    setLoadingDemo(id); setError(null);
    try { const loaded = await apiFetch<{ id: string }>(`/api/v1/demos/${id}`, { method: "POST" }); router.push(`/investigations/${loaded.id}`); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't load demo investigation."); }
    finally { setLoadingDemo(null); }
  }

  return (
    <div>
      <h1 className="font-display text-xl font-medium text-text-primary">Investigations</h1>
      <p className="mt-1 text-sm text-text-muted">
        Includes seeded mock events plus anything real ingested via a connector.
      </p>

      {error && (
        <div className="mt-4 rounded border border-severity-critical/40 bg-severity-critical/10 px-3 py-2 text-sm text-severity-critical">
          {error}
        </div>
      )}

      {investigations?.length === 0 && (
        <Card className="mt-4 border border-signal/40 bg-signal/5">
          <h2 className="font-display text-lg text-text-primary">Welcome to Aegis-AI</h2>
          <p className="mt-2 text-sm text-text-muted">Create an investigation from your evidence, or explore a complete synthetic case in under two minutes.</p>
          <div className="mt-4">
            <p className="text-sm font-medium text-text-primary">🚀 Try Demo Investigation</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {demos.map((demo) => <button key={demo.id} disabled={loadingDemo !== null || demo.loaded} onClick={() => loadDemo(demo.id)} className="rounded bg-signal px-3 py-2 text-xs font-medium text-black disabled:opacity-50">{loadingDemo === demo.id ? "Loading…" : demo.loaded ? `${demo.title} loaded` : demo.title}</button>)}
            </div>
          </div>
        </Card>
      )}

      {investigations && investigations.length > 0 && <div className="mt-4 flex flex-wrap items-center gap-2"><span className="text-xs text-text-muted">Load Demo Investigation:</span>{demos.filter((demo) => !demo.loaded).map((demo) => <button key={demo.id} disabled={loadingDemo !== null} onClick={() => loadDemo(demo.id)} className="rounded border border-hairline px-2 py-1 text-xs text-signal disabled:opacity-50">{loadingDemo === demo.id ? "Loading…" : demo.title}</button>)}</div>}

      <Card className="mt-4 p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hairline text-left text-xs text-text-muted">
              <th className="px-4 py-3 font-normal">Title</th>
              <th className="px-4 py-3 font-normal">Source</th>
              <th className="px-4 py-3 font-normal">Severity</th>
              <th className="px-4 py-3 font-normal">Status</th>
              <th className="px-4 py-3 font-normal">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {investigations === null && !error && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-text-muted">
                  Loading…
                </td>
              </tr>
            )}
            {investigations?.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-text-muted">
                  No investigations yet.
                </td>
              </tr>
            )}
            {investigations?.map((inv) => (
              <tr key={inv.id} className="border-b border-hairline last:border-0 hover:bg-surface-raised">
                <td className="px-4 py-3">
                  <Link href={`/investigations/${inv.id}`} className="text-text-primary hover:text-signal">
                    {inv.title}
                  </Link>
                </td>
                <td className="px-4 py-3 text-text-muted">{inv.source}</td>
                <td className="px-4 py-3">
                  <SeverityBadge severity={inv.severity} />
                </td>
                <td className="px-4 py-3 capitalize text-text-muted">{inv.status}</td>
                <td className="px-4 py-3">
                  <ConfidenceRing value={inv.confidence} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
