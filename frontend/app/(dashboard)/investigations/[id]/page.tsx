"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { apiFetch, ApiError, downloadFile } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { EvidenceExplorer, type EvidenceRecord } from "@/components/investigations/evidence-explorer";
import { IOCDetailOverlay } from "@/components/investigations/ioc-detail";
import { AIReasoningPanel } from "@/components/investigations/ai-reasoning-panel";
import { WorkspaceNav } from "@/components/investigations/workspace-nav";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SeverityBadge } from "@/components/ui/severity-badge";

interface TimelineEvent {
  id: string;
  occurred_at: string;
  description: string;
  severity: string | null;
  mitre_technique: string | null;
  source: string | null;
  affected_asset: string | null;
  actor: string | null;
}

interface RecommendedAction {
  id: string;
  title: string;
  description: string;
  status: string;
  confidence: number | null;
  business_impact: string | null;
  side_effects: string | null;
  rollback: string | null;
  estimated_time_to_contain: string | null;
  approval_tier: string | null;
}

interface Investigation {
  id: string;
  title: string;
  source: string;
  severity: string;
  status: string;
  confidence: number;
  root_cause: string;
  mitre_techniques: string[];
  blast_radius_summary: string;
  false_positive_probability: number;
  attack_chain: { phase: string; description: string }[];
  alternative_hypotheses: { hypothesis: string; likelihood: number }[];
  reasoning_chain: string[];
  created_at: string;
  timeline_events: TimelineEvent[];
  evidence: { id: string; type: string; value: string }[];
  evidence_records: EvidenceRecord[];
  notes: { id: string; body: string; created_at: string }[];
  recommended_actions: RecommendedAction[];
}

const STATUS_TRACK = ["new", "triaging", "investigating", "contained", "resolved"];

const SEVERITY_BORDER: Record<string, string> = {
  critical: "border-severity-critical",
  high: "border-severity-high",
  medium: "border-severity-medium",
  low: "border-severity-low",
  info: "border-severity-info",
};

const NEXT_STATUS: Record<string, string | null> = {
  new: "triaging",
  triaging: "investigating",
  investigating: "contained",
  contained: "resolved",
  resolved: null,
};

export default function InvestigationWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [noteBody, setNoteBody] = useState("");
  const [isSubmittingNote, setIsSubmittingNote] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<TimelineEvent | null>(null);
  const [selectedIOC, setSelectedIOC] = useState<{ type: string; value: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<Investigation>(`/api/v1/investigations/${id}`);
      setInvestigation(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load this investigation.");
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function advanceStatus() {
    if (!investigation) return;
    const next = NEXT_STATUS[investigation.status];
    if (!next) return;
    try {
      await apiFetch(`/api/v1/investigations/${id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: next }),
      });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't update status.");
    }
  }

  async function decideAction(actionId: string, approve: boolean) {
    try {
      await apiFetch(`/api/v1/investigations/actions/${actionId}/${approve ? "approve" : "dismiss"}`, {
        method: "POST",
      });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't update that action.");
    }
  }

  async function submitNote(e: React.FormEvent) {
    e.preventDefault();
    if (!noteBody.trim()) return;
    setIsSubmittingNote(true);
    try {
      await apiFetch(`/api/v1/investigations/${id}/notes`, {
        method: "POST",
        body: JSON.stringify({ body: noteBody }),
      });
      setNoteBody("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't add note.");
    } finally {
      setIsSubmittingNote(false);
    }
  }

  const [downloadingKey, setDownloadingKey] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  async function handleAnalyze() {
    setIsAnalyzing(true);
    setError(null);
    try {
      await apiFetch(`/api/v1/investigations/${id}/intelligence/runs`, {
        method: "POST",
        body: JSON.stringify({ request_key: `legacy-ui:${Date.now().toString(36)}` }),
      });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't queue intelligence analysis.");
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function handleDownload(reportType: "executive" | "technical", format: "markdown" | "pdf") {
    const key = `${reportType}-${format}`;
    setDownloadingKey(key);
    try {
      await downloadFile(`/api/v1/investigations/${id}/report?type=${reportType}&format=${format}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't generate that report.");
    } finally {
      setDownloadingKey(null);
    }
  }

  if (error && !investigation) {
    return (
      <div>
        <button onClick={() => router.push("/investigations")} className="mb-4 text-sm text-text-muted hover:text-text-primary">
          ← Back to investigations
        </button>
        <div className="rounded border border-severity-critical/40 bg-severity-critical/10 px-3 py-2 text-sm text-severity-critical">
          {error}
        </div>
      </div>
    );
  }

  if (!investigation) {
    return <div className="text-sm text-text-muted">Loading…</div>;
  }

  const currentStepIndex = STATUS_TRACK.indexOf(investigation.status);
  const nextStatus = NEXT_STATUS[investigation.status];

  return (
    <div>
      <button onClick={() => router.push("/investigations")} className="mb-4 text-sm text-text-muted hover:text-text-primary">
        ← Back to investigations
      </button>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="font-display text-lg font-medium text-text-primary">{investigation.title}</h1>
          <div className="mt-2 flex items-center gap-1.5 text-xs">
            {STATUS_TRACK.map((step, i) => (
              <span key={step} className="flex items-center gap-1.5">
                <span className={i <= currentStepIndex ? "text-signal" : "text-text-muted"}>
                  {step === investigation.status ? <strong className="capitalize">{step}</strong> : <span className="capitalize">{step}</span>}
                </span>
                {i < STATUS_TRACK.length - 1 && <span className="text-hairline">→</span>}
              </span>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <SeverityBadge severity={investigation.severity} />
          <Link
            href={`/investigations/${investigation.id}/relationships`}
            className="rounded border border-hairline px-3 py-1.5 text-sm text-text-muted hover:border-signal hover:text-signal"
          >
            View attack graph
          </Link>
          {nextStatus && (
            <Button variant="secondary" onClick={advanceStatus}>
              Move to {nextStatus}
            </Button>
          )}
        </div>
      </div>

      <WorkspaceNav investigationId={investigation.id} />

      {error && (
        <div className="mt-4 rounded border border-severity-critical/40 bg-severity-critical/10 px-3 py-2 text-sm text-severity-critical">
          {error}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="text-xs text-text-muted">Generate report:</span>
        {(["executive", "technical"] as const).map((reportType) =>
          (["markdown", "pdf"] as const).map((format) => {
            const key = `${reportType}-${format}`;
            return (
              <button
                key={key}
                onClick={() => handleDownload(reportType, format)}
                disabled={downloadingKey === key}
                className="rounded border border-hairline px-2.5 py-1 text-xs text-text-muted hover:border-signal hover:text-signal disabled:opacity-50"
              >
                {downloadingKey === key
                  ? "Generating…"
                  : `${reportType === "executive" ? "Executive" : "Technical"} · ${format === "pdf" ? "PDF" : "Markdown"}`}
              </button>
            );
          }),
        )}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-[210px_1fr_280px]">
        {/* Timeline */}
        <Card>
          <div className="mb-2 text-xs text-text-muted">Timeline</div>
          <div className="space-y-1">
            {investigation.timeline_events.map((event) => (
              <button
                key={event.id}
                onClick={() => setSelectedEvent(event)}
                className={cn(
                  "block w-full rounded border-l-2 px-2 py-1.5 text-left text-xs transition-colors hover:bg-surface-raised",
                  SEVERITY_BORDER[event.severity ?? "info"],
                )}
              >
                <div className="text-text-muted">{new Date(event.occurred_at).toLocaleString()}</div>
                <div className="mt-0.5 text-text-primary">{event.description}</div>
                <div className="mt-1 flex flex-wrap items-center gap-1">
                  {event.mitre_technique && (
                    <span className="rounded bg-cognition/15 px-1.5 py-0.5 font-mono text-[10px] text-cognition">
                      {event.mitre_technique}
                    </span>
                  )}
                  {event.source && <span className="text-[10px] text-text-muted">{event.source}</span>}
                </div>
              </button>
            ))}
            {investigation.timeline_events.length === 0 && (
              <div className="text-xs text-text-muted">No timeline events.</div>
            )}
          </div>
        </Card>

        {/* Main content: evidence + notes */}
        <Card>
          <div className="mb-2 text-xs text-text-muted">Identified indicators</div>
          <div className="mb-4 flex flex-wrap gap-1.5">
            {investigation.evidence.map((ev) => (
              <button
                key={ev.id}
                onClick={() => setSelectedIOC({ type: ev.type, value: ev.value })}
                className="rounded bg-surface-raised px-2 py-1 font-mono text-[11px] text-text-primary hover:bg-cognition/15 hover:text-cognition"
                title={`${ev.type} — click for IOC intelligence`}
              >
                {ev.value}
              </button>
            ))}
            {investigation.evidence.length === 0 && <span className="text-xs text-text-muted">None recorded.</span>}
          </div>

          <div className="mb-4">
            <EvidenceExplorer records={investigation.evidence_records} />
          </div>

          <div className="mb-2 text-xs text-text-muted">Notes</div>
          <div className="mb-3 space-y-2">
            {investigation.notes.map((note) => (
              <div key={note.id} className="rounded border border-hairline p-2 text-xs">
                <div className="text-text-primary">{note.body}</div>
                <div className="mt-1 text-text-muted">{new Date(note.created_at).toLocaleString()}</div>
              </div>
            ))}
          </div>
          <form onSubmit={submitNote} className="flex gap-2">
            <input
              value={noteBody}
              onChange={(e) => setNoteBody(e.target.value)}
              placeholder="Add a note…"
              className="flex-1 rounded border border-hairline bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted"
            />
            <Button type="submit" disabled={isSubmittingNote || !noteBody.trim()}>
              Add
            </Button>
          </form>
        </Card>

        {/* AI reasoning panel */}
        <AIReasoningPanel
          confidence={investigation.confidence}
          rootCause={investigation.root_cause}
          mitreTechniques={investigation.mitre_techniques}
          blastRadiusSummary={investigation.blast_radius_summary}
          falsePositiveProbability={investigation.false_positive_probability}
          attackChain={investigation.attack_chain}
          alternativeHypotheses={investigation.alternative_hypotheses}
          reasoningChain={investigation.reasoning_chain}
          recommendedActions={investigation.recommended_actions}
          isAnalyzing={isAnalyzing}
          onAnalyze={handleAnalyze}
          onDecideAction={decideAction}
        />
      </div>

      {selectedEvent && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          onClick={() => setSelectedEvent(null)}
        >
          <div
            className="w-full max-w-md rounded-card border border-hairline bg-surface p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between">
              <div className="text-xs text-text-muted">{new Date(selectedEvent.occurred_at).toLocaleString()}</div>
              <button onClick={() => setSelectedEvent(null)} className="text-text-muted hover:text-text-primary">
                ✕
              </button>
            </div>
            <div className="mt-2 text-sm text-text-primary">{selectedEvent.description}</div>

            <dl className="mt-4 space-y-2 text-xs">
              <div className="flex justify-between border-b border-hairline pb-2">
                <dt className="text-text-muted">Severity</dt>
                <dd>{selectedEvent.severity ? <SeverityBadge severity={selectedEvent.severity} /> : "—"}</dd>
              </div>
              <div className="flex justify-between border-b border-hairline pb-2">
                <dt className="text-text-muted">MITRE technique</dt>
                <dd className="font-mono text-text-primary">{selectedEvent.mitre_technique ?? "—"}</dd>
              </div>
              <div className="flex justify-between border-b border-hairline pb-2">
                <dt className="text-text-muted">Source</dt>
                <dd className="text-text-primary">{selectedEvent.source ?? "—"}</dd>
              </div>
              <div className="flex justify-between border-b border-hairline pb-2">
                <dt className="text-text-muted">Affected asset</dt>
                <dd className="font-mono text-text-primary">{selectedEvent.affected_asset ?? "—"}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-text-muted">Actor</dt>
                <dd className="font-mono text-text-primary">{selectedEvent.actor ?? "—"}</dd>
              </div>
            </dl>
          </div>
        </div>
      )}

      {selectedIOC && (
        <IOCDetailOverlay
          type={selectedIOC.type}
          value={selectedIOC.value}
          excludeInvestigationId={investigation.id}
          onClose={() => setSelectedIOC(null)}
        />
      )}
    </div>
  );
}
