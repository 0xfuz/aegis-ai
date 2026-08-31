"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ApiError, apiFetch } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DegradedState, EmptyState, LoadingState, NotFoundState, PermissionDeniedState, RetryableErrorState } from "@/components/ui/async-state";
import { WorkspaceNav } from "./workspace-nav";

type Note = { id: string; author_id: string; body: string; created_at: string; updated_at: string };
type NotePage = { items: Note[]; limit: number; offset: number; total: number };
type State = "loading" | "ready" | "denied" | "not-found" | "degraded" | "error";
const PAGE_SIZE = 25;
const MAX_LENGTH = 4000;

function listPath(id: string, offset: number) { return `/api/v1/investigations/${encodeURIComponent(id)}/notes?limit=${PAGE_SIZE}&offset=${offset}`; }
function displayTime(value: string) { return new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short", timeZone: "UTC" }).format(new Date(value)); }

export function NotesWorkspace({ id }: { id: string }) {
  const { hasPermission } = useAuth();
  const [page, setPage] = useState<NotePage | null>(null); const [offset, setOffset] = useState(0); const [state, setState] = useState<State>("loading"); const [revision, setRevision] = useState(0);
  const [body, setBody] = useState(""); const [submitting, setSubmitting] = useState(false); const [createError, setCreateError] = useState<string | null>(null);
  const controllers = useRef(new Set<AbortController>());
  const canWrite = hasPermission("investigation:write");
  const load = useCallback(async (signal?: AbortSignal) => {
    if (!id) { setState("not-found"); return; }
    setState("loading");
    try { const next = await apiFetch<NotePage>(listPath(id, offset), { signal }); if (!signal?.aborted) { setPage(next); setState("ready"); } }
    catch (error) { if (signal?.aborted) return; if (error instanceof ApiError) setState(error.status === 403 ? "denied" : error.status === 404 ? "not-found" : error.status === 503 ? "degraded" : "error"); else setState("error"); }
  }, [id, offset]);
  useEffect(() => {
    const next = new AbortController();
    controllers.current.add(next);
    void load(next.signal).finally(() => controllers.current.delete(next));
    return () => next.abort();
  }, [load, revision]);
  useEffect(() => () => { controllers.current.forEach(controller => controller.abort()); }, []);
  useEffect(() => { setOffset(0); }, [id]);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); const text = body.trim(); if (!canWrite || submitting || !text || text.length > MAX_LENGTH) return;
    setSubmitting(true); setCreateError(null); const next = new AbortController(); controllers.current.add(next);
    try { await apiFetch(`/api/v1/investigations/${encodeURIComponent(id)}/notes`, { method: "POST", body: JSON.stringify({ body: text }), signal: next.signal }); if (!next.signal.aborted) { setBody(""); setOffset(0); setRevision(value => value + 1); } }
    catch (error) { if (!next.signal.aborted) setCreateError(error instanceof ApiError && error.status === 503 ? "Notes are temporarily unavailable." : "Unable to save note. Please try again."); }
    finally { controllers.current.delete(next); if (!next.signal.aborted) setSubmitting(false); }
  };
  const shownFrom = page?.total ? page.offset + 1 : 0; const shownTo = page ? Math.min(page.offset + page.items.length, page.total) : 0;
  return <><div className="mb-2 text-xs text-text-muted"><Link href="/investigations">Cases</Link> / Investigation workspace</div><h1 className="font-display text-lg text-text-primary">Notes</h1><WorkspaceNav investigationId={id} />
    {state === "loading" && <LoadingState title="Loading notes" message="Loading authorized Investigation notes." />}{state === "denied" && <PermissionDeniedState />}{state === "not-found" && <NotFoundState />}{state === "degraded" && <div className="space-y-3"><DegradedState message="Notes are temporarily unavailable." /><Button type="button" variant="secondary" onClick={() => setRevision(value => value + 1)}>Retry</Button></div>}{state === "error" && <RetryableErrorState title="Unable to load notes" message="Notes could not be loaded. Please try again." onRetry={() => setRevision(value => value + 1)} />}
    {state === "ready" && page && <><section aria-labelledby="notes-help" className="mb-4"><h2 id="notes-help" className="font-display text-base">Analyst notes</h2><p className="text-sm text-text-muted">Notes are authored by analysts and remain separate from Findings, claims, and automated actions.</p></section>
      {canWrite && <Card className="mb-4"><form onSubmit={submit}><label className="block text-sm font-medium" htmlFor="note-body">Add note</label><textarea id="note-body" value={body} maxLength={MAX_LENGTH} onChange={event => setBody(event.target.value)} className="mt-2 min-h-28 w-full rounded border border-hairline bg-surface p-2 text-sm" aria-describedby="note-guidance" disabled={submitting} /><p id="note-guidance" className="mt-1 text-xs text-text-muted">{body.length}/{MAX_LENGTH} characters. Empty notes are not saved.</p>{createError && <p role="alert" className="mt-2 text-sm text-severity-critical">{createError}</p>}<Button type="submit" className="mt-3" disabled={submitting || !body.trim() || body.trim().length > MAX_LENGTH}>{submitting ? "Saving note…" : "Save note"}</Button></form></Card>}
      {page.items.length === 0 ? <EmptyState title="No notes" message="No analyst notes have been recorded for this Investigation." /> : <section aria-labelledby="note-list"><div className="mb-2 flex flex-wrap justify-between gap-2"><h2 id="note-list" className="font-display text-base">Notes</h2><p aria-live="polite" className="text-xs text-text-muted">Showing {shownFrom}–{shownTo} of {page.total} notes. Server order: newest first.</p></div><ol className="space-y-3">{page.items.map(note => <li key={note.id}><Card><p className="whitespace-pre-wrap break-words text-sm">{note.body}</p><dl className="mt-3 grid gap-1 text-xs text-text-muted"><div><dt className="inline">Author: </dt><dd className="inline font-mono">{note.author_id}</dd></div><div><dt className="inline">Created (UTC): </dt><dd className="inline">{displayTime(note.created_at)}</dd></div></dl></Card></li>)}</ol><nav className="mt-4 flex justify-between" aria-label="Notes pagination"><Button type="button" variant="secondary" disabled={page.offset === 0} onClick={() => setOffset(value => Math.max(0, value - PAGE_SIZE))}>Previous</Button><Button type="button" variant="secondary" disabled={page.offset + page.items.length >= page.total} onClick={() => setOffset(value => value + PAGE_SIZE)}>Next</Button></nav></section>}</>}
  </>;
}
