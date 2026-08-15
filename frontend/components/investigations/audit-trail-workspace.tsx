"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DegradedState, EmptyState, LoadingState, NotFoundState, PermissionDeniedState, RetryableErrorState } from "@/components/ui/async-state";
import { WorkspaceNav } from "./workspace-nav";

type AuditEvent = {
  id: string;
  event_type: string;
  occurred_at: string;
  actor: { type: string; id: string | null };
  target: { type: string; id: string };
  transition: { from: string | null; to: string | null } | null;
};
type AuditPage = { items: AuditEvent[]; limit: number; offset: number; total: number };
type AuditState = "loading" | "ready" | "denied" | "not-found" | "degraded" | "error";

const PAGE_SIZE = 25;

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit", timeZoneName: "short" }).format(new Date(value));
}

function auditPath(id: string, offset: number) {
  return `/api/v1/investigations/${encodeURIComponent(id)}/audit?limit=${PAGE_SIZE}&offset=${offset}`;
}

export function AuditTrailWorkspace({ id }: { id: string }) {
  const [page, setPage] = useState<AuditPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [state, setState] = useState<AuditState>("loading");
  const [revision, setRevision] = useState(0);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!id) { setState("not-found"); return; }
    setState("loading");
    try {
      const result = await apiFetch<AuditPage>(auditPath(id, offset), { signal });
      if (!signal?.aborted) { setPage(result); setState("ready"); }
    } catch (error) {
      if (signal?.aborted) return;
      if (error instanceof ApiError) {
        setState(error.status === 403 ? "denied" : error.status === 404 ? "not-found" : error.status === 503 ? "degraded" : "error");
      } else setState("error");
    }
  }, [id, offset]);

  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [load, revision]);
  useEffect(() => { setOffset(0); }, [id]);

  const retry = () => setRevision(value => value + 1);
  const shownFrom = page?.total ? page.offset + 1 : 0;
  const shownTo = page ? Math.min(page.offset + page.items.length, page.total) : 0;

  return <>
    <div className="mb-2 text-xs text-text-muted"><Link href="/investigations">Cases</Link> / Investigation workspace</div>
    <h1 className="font-display text-lg text-text-primary">Audit Trail</h1>
    <WorkspaceNav investigationId={id} />
    {state === "loading" && <LoadingState title="Loading audit trail" message="Loading authorized Investigation audit events." />}
    {state === "denied" && <PermissionDeniedState />}
    {state === "not-found" && <NotFoundState />}
    {state === "degraded" && <div className="space-y-3"><DegradedState message="Audit events are temporarily unavailable." /><Button type="button" variant="secondary" onClick={retry}>Retry</Button></div>}
    {state === "error" && <RetryableErrorState title="Unable to load audit trail" message="Audit events could not be loaded. Please try again." onRetry={retry} />}
    {state === "ready" && page && (page.items.length === 0 ? <EmptyState title="No audit events" message="No authorized audit events have been recorded for this Investigation." /> : <Card>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div><h2 className="font-display text-base">Chronological audit events</h2><p className="text-xs text-text-muted">Server order: newest first. Time is displayed in your local timezone.</p></div>
        <p aria-live="polite" className="text-xs text-text-muted">Showing {shownFrom}–{shownTo} of {page.total} audit events</p>
      </div>
      <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead className="text-text-muted"><tr><th className="pb-2">Event type</th><th className="pb-2">Time (local timezone)</th><th className="pb-2">Actor</th><th className="pb-2">Target</th><th className="pb-2">Safe transition</th></tr></thead><tbody>{page.items.map(event => <tr className="border-t border-hairline align-top" key={event.id}><td className="py-3 font-medium">{event.event_type}</td><td className="py-3 whitespace-nowrap">{formatTime(event.occurred_at)}</td><td className="py-3">{event.actor.type}{event.actor.id ? <><br /><span className="font-mono text-text-muted">{event.actor.id}</span></> : null}</td><td className="py-3">{event.target.type}<br /><span className="font-mono text-text-muted">{event.target.id}</span></td><td className="py-3">{event.transition ? <span>{event.transition.from ?? "Previous state unavailable"} → {event.transition.to ?? "Current state unavailable"}</span> : <span className="text-text-muted">No state transition recorded</span>}</td></tr>)}</tbody></table></div>
      <nav className="mt-4 flex items-center justify-between" aria-label="Audit trail pagination"><Button type="button" variant="secondary" disabled={page.offset === 0} onClick={() => setOffset(value => Math.max(0, value - PAGE_SIZE))}>Previous</Button><Button type="button" variant="secondary" disabled={page.offset + page.items.length >= page.total} onClick={() => setOffset(value => value + PAGE_SIZE)}>Next</Button></nav>
    </Card>)}
  </>;
}
