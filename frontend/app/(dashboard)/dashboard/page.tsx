"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api-client";
import { Card, CardLabel, CardValue } from "@/components/ui/card";
import { SeverityBadge } from "@/components/ui/severity-badge";
import { ConfidenceRing } from "@/components/ui/confidence-ring";

interface DashboardSummary {
  open_investigations: number;
  critical_open: number;
  avg_false_positive_probability: number;
  total_investigations: number;
}

interface InvestigationSummary {
  id: string;
  title: string;
  severity: string;
  status: string;
  confidence: number;
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [queue, setQueue] = useState<InvestigationSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<DashboardSummary>("/api/v1/investigations/dashboard-summary"),
      apiFetch<InvestigationSummary[]>("/api/v1/investigations?limit=5"),
    ])
      .then(([summaryData, queueData]) => {
        setSummary(summaryData);
        setQueue(queueData);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load dashboard data."));
  }, []);

  return (
    <div>
      <h1 className="font-display text-xl font-medium text-text-primary">Dashboard</h1>
      <p className="mt-1 text-sm text-text-muted">
        Includes seeded mock events plus anything real ingested via a connector.
      </p>

      {error && (
        <div className="mt-4 rounded border border-severity-critical/40 bg-severity-critical/10 px-3 py-2 text-sm text-severity-critical">
          {error}
        </div>
      )}

      <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Card>
          <CardLabel>Open investigations</CardLabel>
          <CardValue>{summary?.open_investigations ?? "—"}</CardValue>
        </Card>
        <Card>
          <CardLabel>Critical open</CardLabel>
          <CardValue className="text-severity-critical">{summary?.critical_open ?? "—"}</CardValue>
        </Card>
        <Card>
          <CardLabel>Total investigations</CardLabel>
          <CardValue>{summary?.total_investigations ?? "—"}</CardValue>
        </Card>
        <Card>
          <CardLabel>Avg. false-positive probability</CardLabel>
          <CardValue className="text-signal">
            {summary ? `${summary.avg_false_positive_probability}%` : "—"}
          </CardValue>
        </Card>
      </div>

      <Card className="mt-4 p-0">
        <div className="flex items-center justify-between border-b border-hairline px-4 py-3">
          <span className="text-xs text-text-muted">Investigation queue</span>
          <Link href="/investigations" className="text-xs text-signal hover:underline">
            View all
          </Link>
        </div>
        {queue?.map((inv) => (
          <Link
            key={inv.id}
            href={`/investigations/${inv.id}`}
            className="flex items-center justify-between border-b border-hairline px-4 py-3 last:border-0 hover:bg-surface-raised"
          >
            <div className="flex items-center gap-2">
              <SeverityBadge severity={inv.severity} />
              <span className="text-sm text-text-primary">{inv.title}</span>
            </div>
            <ConfidenceRing value={inv.confidence} />
          </Link>
        ))}
        {queue?.length === 0 && (
          <div className="px-4 py-6 text-center text-sm text-text-muted">No investigations yet.</div>
        )}
        {queue === null && !error && (
          <div className="px-4 py-6 text-center text-sm text-text-muted">Loading…</div>
        )}
      </Card>
    </div>
  );
}
