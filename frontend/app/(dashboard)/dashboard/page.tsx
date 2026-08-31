"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardLabel, CardValue } from "@/components/ui/card";
import { SeverityBadge } from "@/components/ui/severity-badge";
import { ConfidenceRing } from "@/components/ui/confidence-ring";
import { DegradedState, EmptyState, LoadingState, NotFoundState, PermissionDeniedState, RetryableErrorState } from "@/components/ui/async-state";

type DashboardWindow = { preset: string | null; from_at: string; to_at: string };
type DashboardSummary = { open_investigations: number; critical_open: number; avg_false_positive_probability: number; total_investigations: number; window: DashboardWindow | null };
type InvestigationSummary = { id: string; title: string; severity: string; status: string; confidence: number };
type InvestigationPage = { items: InvestigationSummary[] };
type ViewState = "loading" | "ready" | "denied" | "not-found" | "degraded" | "error";
const PRESETS = [{ value: "24h", label: "24 hours" }, { value: "7d", label: "7 days" }, { value: "30d", label: "30 days" }];

function utcLabel(value: string) { return new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "UTC", timeZoneName: "short" }).format(new Date(value)); }
function dashboardPath(preset: string, fromAt: string, toAt: string) {
  const query = new URLSearchParams();
  if (preset) query.set("window", preset); else if (fromAt && toAt) { query.set("from", new Date(`${fromAt}:00Z`).toISOString()); query.set("to", new Date(`${toAt}:00Z`).toISOString()); }
  const rendered = query.toString();
  return `/api/v1/investigations/dashboard-summary${rendered ? `?${rendered}` : ""}`;
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [queue, setQueue] = useState<InvestigationSummary[] | null>(null);
  const [view, setView] = useState<ViewState>("loading");
  const [preset, setPreset] = useState(""); const [fromAt, setFromAt] = useState(""); const [toAt, setToAt] = useState(""); const [validation, setValidation] = useState<string | null>(null); const [revision, setRevision] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const load = useCallback(async () => {
    controller.current?.abort(); const next = new AbortController(); controller.current = next; setView("loading");
    try {
      const [summaryData, queueData] = await Promise.all([apiFetch<DashboardSummary>(dashboardPath(preset, fromAt, toAt), { signal: next.signal }), apiFetch<InvestigationPage>("/api/v1/investigations?limit=5", { signal: next.signal })]);
      if (!next.signal.aborted) { setSummary(summaryData); setQueue(queueData.items); setView("ready"); }
    } catch (error) {
      if (next.signal.aborted) return;
      setView(error instanceof ApiError ? error.status === 403 ? "denied" : error.status === 404 ? "not-found" : error.status === 503 ? "degraded" : "error" : "error");
    }
  }, [preset, fromAt, toAt]);
  useEffect(() => { void load(); return () => controller.current?.abort(); }, [load, revision]);
  function apply(event: FormEvent) { event.preventDefault(); if ((!fromAt) !== (!toAt)) return setValidation("Enter both From and To times."); if (fromAt && toAt && new Date(fromAt) > new Date(toAt)) return setValidation("From must not be later than To."); setValidation(null); setRevision(value => value + 1); }
  function choosePreset(value: string) { setPreset(value); setFromAt(""); setToAt(""); setValidation(null); setRevision(count => count + 1); }
  function clear() { setPreset(""); setFromAt(""); setToAt(""); setValidation(null); setRevision(count => count + 1); }
  const active = summary?.window;
  return <div>
    <h1 className="font-display text-xl font-medium text-text-primary">Dashboard</h1><p className="mt-1 text-sm text-text-muted">Organization-scoped operational summary.</p>
    <Card className="mt-5"><form onSubmit={apply} aria-describedby="dashboard-window-help"><fieldset><legend className="font-display text-base text-text-primary">Dashboard time window</legend><p id="dashboard-window-help" className="mt-1 text-sm text-text-muted">All counts use UTC and include From while excluding To.</p><div className="mt-3 flex flex-wrap gap-2" aria-label="Dashboard preset windows">{PRESETS.map(option => <Button key={option.value} type="button" variant={preset === option.value ? "primary" : "secondary"} onClick={() => choosePreset(option.value)}>{option.label}</Button>)}</div><div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="text-sm">From (UTC)<input type="datetime-local" value={fromAt} disabled={Boolean(preset)} onChange={event => setFromAt(event.target.value)} className="mt-1 block w-full rounded border border-hairline bg-surface p-2" /></label><label className="text-sm">To (UTC)<input type="datetime-local" value={toAt} disabled={Boolean(preset)} onChange={event => setToAt(event.target.value)} className="mt-1 block w-full rounded border border-hairline bg-surface p-2" /></label></div>{validation && <p role="alert" className="mt-2 text-sm text-severity-critical">{validation}</p>}<div className="mt-4 flex gap-2"><Button type="submit">Apply</Button><Button type="button" variant="secondary" onClick={clear}>Clear</Button></div></fieldset></form></Card>
    {active && <p className="mt-3 text-sm text-text-muted" aria-live="polite">Active window: {active.preset ? PRESETS.find(item => item.value === active.preset)?.label : "Custom UTC range"} — {utcLabel(active.from_at)} to {utcLabel(active.to_at)} (end excluded).</p>}
    {view === "loading" && <div className="mt-4"><LoadingState title="Loading dashboard" message="Loading server-authoritative operational counts." /></div>}{view === "denied" && <div className="mt-4"><PermissionDeniedState /></div>}{view === "not-found" && <div className="mt-4"><NotFoundState /></div>}{view === "degraded" && <div className="mt-4"><DegradedState /><Button type="button" variant="secondary" className="mt-3" onClick={() => setRevision(value => value + 1)}>Retry</Button></div>}{view === "error" && <div className="mt-4"><RetryableErrorState onRetry={() => setRevision(value => value + 1)} message="Dashboard data is temporarily unavailable." /></div>}
    {view === "ready" && summary && <><div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4"><Card><CardLabel>Open investigations</CardLabel><CardValue>{summary.open_investigations}</CardValue></Card><Card><CardLabel>Critical open</CardLabel><CardValue className="text-severity-critical">{summary.critical_open}</CardValue></Card><Card><CardLabel>Total investigations</CardLabel><CardValue>{summary.total_investigations}</CardValue></Card><Card><CardLabel>Avg. false-positive probability</CardLabel><CardValue className="text-signal">{summary.avg_false_positive_probability}%</CardValue></Card></div>{summary.total_investigations === 0 && <div className="mt-4"><EmptyState title="No cases in this window" message="No Investigation records fall within the selected UTC window." /></div>}<Card className="mt-4 p-0"><div className="flex items-center justify-between border-b border-hairline px-4 py-3"><span className="text-xs text-text-muted">Latest Investigation queue</span><Link href="/investigations" className="text-xs text-signal hover:underline focus-visible:outline">View all Cases</Link></div>{queue?.map(inv => <Link key={inv.id} href={`/investigations/${inv.id}`} className="flex items-center justify-between border-b border-hairline px-4 py-3 last:border-0 hover:bg-surface-raised focus-visible:outline"><div className="min-w-0 flex items-center gap-2"><SeverityBadge severity={inv.severity} /><span className="truncate text-sm text-text-primary">{inv.title}</span></div><ConfidenceRing value={inv.confidence} /></Link>)}{queue?.length === 0 && <div className="px-4 py-6 text-center text-sm text-text-muted">No Cases are available.</div>}</Card></>}</div>;
}
