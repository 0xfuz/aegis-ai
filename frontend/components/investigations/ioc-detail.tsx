"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api-client";
import { SeverityBadge } from "@/components/ui/severity-badge";
import { VerdictBadge } from "@/components/ui/verdict-badge";
import { Button } from "@/components/ui/button";

interface RelatedInvestigation {
  id: string;
  title: string;
  severity: string;
  status: string;
}

interface RelatedEvidenceRecord {
  id: string;
  category: string;
  occurred_at: string;
  summary: string;
  details: Record<string, unknown>;
}

interface IOCDetail {
  type: string;
  value: string;
  tags: string[];
  confidence: number;
  verdict: string;
  provenance: string;
  is_watched: boolean;
  watched_at: string | null;
  enrichment: Record<string, unknown>;
  first_seen: string;
  last_seen: string;
  sightings_count: number;
  related_investigations: RelatedInvestigation[];
  related_assets: string[];
  related_evidence: RelatedEvidenceRecord[];
}

/** Explicit provenance labeling — must never imply a real external feed
 * was queried when it wasn't. "internal" covers seed/analyst curation;
 * anything else is a real provider's own key (none registered yet). */
function ProvenanceLabel({ provenance }: { provenance: string }) {
  const isInternal = provenance === "internal";
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] " +
        (isInternal ? "bg-text-muted/15 text-text-muted" : "bg-signal/15 text-signal")
      }
      title={
        isInternal
          ? "Curated within Aegis (seed data or analyst action) — no external feed was queried."
          : `Enriched by external provider: ${provenance}`
      }
    >
      {isInternal ? "Internal — no external lookup performed" : `External: ${provenance}`}
    </span>
  );
}

export function IOCDetailOverlay({
  type,
  value,
  excludeInvestigationId,
  onClose,
}: {
  type: string;
  value: string;
  excludeInvestigationId?: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<IOCDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [watchPending, setWatchPending] = useState(false);
  const [watchError, setWatchError] = useState<string | null>(null);

  function load() {
    const excludeParam = excludeInvestigationId
      ? `&exclude_investigation_id=${excludeInvestigationId}`
      : "";
    apiFetch<IOCDetail>(
      `/api/v1/investigations/iocs/lookup?type=${encodeURIComponent(type)}&value=${encodeURIComponent(value)}${excludeParam}`,
    )
      .then((d) => {
        setDetail(d);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load indicator intelligence."));
  }

  useEffect(() => {
    setDetail(null);
    setError(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, value, excludeInvestigationId]);

  async function toggleWatch() {
    if (!detail) return;
    setWatchPending(true);
    setWatchError(null);
    try {
      const updated = await apiFetch<IOCDetail>("/api/v1/investigations/iocs/watch", {
        method: "POST",
        body: JSON.stringify({ type, value, watched: !detail.is_watched }),
      });
      setDetail(updated);
    } catch (err) {
      setWatchError(err instanceof ApiError ? err.message : "Couldn't update the watchlist.");
    } finally {
      setWatchPending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-card border border-hairline bg-surface p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-mono text-sm text-text-primary">{value}</div>
            <div className="mt-0.5 text-[11px] uppercase tracking-wide text-text-muted">{type}</div>
          </div>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary">
            ✕
          </button>
        </div>

        {error && <div className="mt-4 text-xs text-severity-critical">{error}</div>}

        {!detail && !error && <div className="mt-4 text-xs text-text-muted">Loading…</div>}

        {detail && (
          <>
            <div className="mt-4 flex flex-wrap items-center gap-4">
              <div>
                <div className="text-[11px] text-text-muted">Confidence (malicious)</div>
                <div className="font-display text-lg font-medium text-text-primary">{detail.confidence}%</div>
              </div>
              <div>
                <div className="text-[11px] text-text-muted">Sightings</div>
                <div className="font-display text-lg font-medium text-text-primary">{detail.sightings_count}</div>
              </div>
              <div>
                <div className="text-[11px] text-text-muted">Verdict</div>
                <div className="mt-0.5">
                  <VerdictBadge verdict={detail.verdict} />
                </div>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <ProvenanceLabel provenance={detail.provenance} />
            </div>

            <div className="mt-3">
              <Button
                variant={detail.is_watched ? "secondary" : "primary"}
                onClick={toggleWatch}
                disabled={watchPending}
                className="w-full justify-center"
              >
                {watchPending
                  ? "Updating…"
                  : detail.is_watched
                    ? "★ Watching — remove from watchlist"
                    : "☆ Add to watchlist"}
              </Button>
              {detail.is_watched && detail.watched_at && (
                <div className="mt-1 text-center text-[11px] text-text-muted">
                  Watched since {new Date(detail.watched_at).toLocaleDateString()}
                </div>
              )}
              {watchError && <div className="mt-1 text-center text-xs text-severity-critical">{watchError}</div>}
            </div>

            {detail.tags.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {detail.tags.map((tag) => (
                  <span key={tag} className="rounded-full bg-severity-critical/15 px-2 py-0.5 text-[10px] text-severity-critical">
                    {tag}
                  </span>
                ))}
              </div>
            )}

            <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-text-muted">
              <div>First seen: {new Date(detail.first_seen).toLocaleDateString()}</div>
              <div>Last seen: {new Date(detail.last_seen).toLocaleDateString()}</div>
            </div>

            {Object.keys(detail.enrichment).length > 0 && (
              <div className="mt-4">
                <div className="mb-1.5 text-xs text-text-muted">Enrichment</div>
                <dl className="space-y-1.5 text-xs">
                  {Object.entries(detail.enrichment).map(([key, val]) => (
                    <div key={key} className="flex justify-between gap-4 border-b border-hairline pb-1.5 last:border-0">
                      <dt className="capitalize text-text-muted">{key.replace(/_/g, " ")}</dt>
                      <dd className="text-right text-text-primary">{String(val)}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}

            <div className="mt-4">
              <div className="mb-1.5 text-xs text-text-muted">
                Related investigations ({detail.related_investigations.length})
              </div>
              {detail.related_investigations.length === 0 ? (
                <div className="text-xs text-text-muted">Not seen in any other investigation.</div>
              ) : (
                <div className="space-y-1.5">
                  {detail.related_investigations.map((inv) => (
                    <Link
                      key={inv.id}
                      href={`/investigations/${inv.id}`}
                      className="flex items-center justify-between rounded border border-hairline px-2 py-1.5 text-xs hover:bg-surface-raised"
                    >
                      <span className="text-text-primary">{inv.title}</span>
                      <SeverityBadge severity={inv.severity} />
                    </Link>
                  ))}
                </div>
              )}
            </div>

            <div className="mt-4">
              <div className="mb-1.5 text-xs text-text-muted">
                Related assets ({detail.related_assets.length})
              </div>
              {detail.related_assets.length === 0 ? (
                <div className="text-xs text-text-muted">No assets seen alongside this indicator.</div>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {detail.related_assets.map((name) => (
                    <span
                      key={name}
                      title="Seen in the same investigation as this indicator — the Assets page doesn't yet support opening a specific asset by name."
                      className="rounded border border-hairline px-2 py-1 font-mono text-[11px] text-text-primary"
                    >
                      {name}
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="mt-4">
              <div className="mb-1.5 text-xs text-text-muted">
                Related evidence ({detail.related_evidence.length})
              </div>
              {detail.related_evidence.length === 0 ? (
                <div className="text-xs text-text-muted">
                  No Evidence Explorer records reference this value.
                </div>
              ) : (
                <div className="space-y-1.5">
                  {detail.related_evidence.map((rec) => (
                    <div key={rec.id} className="rounded border border-hairline px-2 py-1.5 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="uppercase text-[10px] text-text-muted">
                          {rec.category.replace(/_/g, " ")}
                        </span>
                        <span className="text-[10px] text-text-muted">
                          {new Date(rec.occurred_at).toLocaleDateString()}
                        </span>
                      </div>
                      <div className="mt-0.5 text-text-primary">{rec.summary}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
