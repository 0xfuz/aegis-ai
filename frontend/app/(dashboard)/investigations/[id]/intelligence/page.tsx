"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { EmptyState, NotFoundState, PermissionDeniedState, RetryableErrorState } from "@/components/ui/async-state";
import { WorkspaceNav } from "@/components/investigations/workspace-nav";
import { useInvestigationReconstruction } from "@/lib/use-investigation-reconstruction";
import { useInvestigationIntelligenceRun } from "@/lib/use-investigation-intelligence-run";
import { IntelligenceRunProgress } from "@/components/investigations/intelligence-run-progress";
import { IntelligenceRunHistory } from "@/components/investigations/intelligence-run-history";
import { ReconstructionExplanation } from "@/components/investigations/reconstruction-explanation";
import { CitationList, ClaimExplanationPanel, PromotionExplanationPanel, type IntelligenceAnalysisRead } from "@/components/investigations/claim-citation-explanation";
import { fetchIntelligenceAnalysis } from "@/lib/intelligence-run-client";

type Analysis = IntelligenceAnalysisRead;
type AnalysisError = "forbidden" | "not_found" | "unavailable";

function safeAnalysisError(error: unknown): AnalysisError {
  if (error instanceof ApiError && error.status === 403) return "forbidden";
  if (error instanceof ApiError && error.status === 404) return "not_found";
  return "unavailable";
}

export default function IntelligencePage() {
  const { id } = useParams<{ id: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, hasPermission } = useAuth();
  const requestedRunId = searchParams.get("run_id");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analysisError, setAnalysisError] = useState<AnalysisError | null>(null);
  const [completedRefresh, setCompletedRefresh] = useState(0);
  const analysisRequestSequence = useRef(0);
  const intelligenceRun = useInvestigationIntelligenceRun(id, useCallback(() => setCompletedRefresh((value) => value + 1), []), requestedRunId);
  const selectedRunId = intelligenceRun.run?.status === "COMPLETED" ? intelligenceRun.run.id : null;
  const reconstruction = useInvestigationReconstruction(id, selectedRunId);

  const loadAnalysis = useCallback(async () => {
    const sequence = ++analysisRequestSequence.current;
    if (!selectedRunId) { setAnalysis(null); setAnalysisError(null); return; }
    try {
      const next = await fetchIntelligenceAnalysis<Analysis>(id, selectedRunId);
      if (sequence === analysisRequestSequence.current) { setAnalysis(next); setAnalysisError(null); }
    } catch (error) {
      if (sequence === analysisRequestSequence.current) { setAnalysis(null); setAnalysisError(safeAnalysisError(error)); }
    }
  }, [id, selectedRunId]);
  useEffect(() => { void loadAnalysis(); }, [completedRefresh, loadAnalysis]);

  const selectCompletedRun = useCallback((runId: string) => {
    intelligenceRun.selectCompletedRun(runId);
    const query = new URLSearchParams(searchParams.toString());
    query.set("run_id", runId);
    router.replace(`${pathname}?${query}`);
  }, [intelligenceRun, pathname, router, searchParams]);
  const canWrite = Boolean(user?.is_active && hasPermission("investigation:write"));
  const citations = reconstruction.status === "ready" ? reconstruction.data.sections.citations : [];

  return <main aria-labelledby="intelligence-heading">
    <div className="mb-2 text-xs text-text-muted"><Link href="/investigations">Cases</Link> / Investigation Intelligence</div>
    <h1 id="intelligence-heading" className="font-display text-lg">Investigation Intelligence</h1>
    <WorkspaceNav investigationId={id} />
    <section aria-labelledby="factual-reconstruction" className="mt-4">
      <h2 id="factual-reconstruction" className="sr-only">Certified factual reconstruction</h2>
      {reconstruction.status === "loading" && <p aria-live="polite" className="mb-3 text-xs text-text-muted">Loading certified factual reconstruction…</p>}
      {reconstruction.status === "ready" && <><ReconstructionExplanation investigationId={id} data={reconstruction.data} /><PromotionExplanationPanel data={reconstruction.data} /><CitationList data={reconstruction.data} selectedRunId={selectedRunId} /></>}
      {reconstruction.status === "forbidden" && <PermissionDeniedState />}
      {reconstruction.status === "not_found" && <NotFoundState />}
      {reconstruction.status === "invalid" && <NotFoundState />}
      {reconstruction.status === "error" && <RetryableErrorState title="Reconstruction unavailable" message="The certified factual reconstruction could not be loaded." onRetry={reconstruction.retry} />}
    </section>
    <section aria-labelledby="run-controls" className="mt-5">
      <h2 id="run-controls" className="font-display text-base">Intelligence Run</h2>
      {canWrite ? <div className="mt-2 flex flex-wrap items-center gap-2"><Button onClick={() => void intelligenceRun.submit()} disabled={intelligenceRun.initializing || intelligenceRun.submitting || intelligenceRun.active}>Run analysis</Button><span className="text-xs text-text-muted">AI claims are reviewable and never FACT.</span></div> : <p className="mt-2 text-sm text-text-muted">You can view authoritative run and claim status, but cannot start or review analysis.</p>}
      <IntelligenceRunProgress run={intelligenceRun.latestRun} submitting={intelligenceRun.submitting} initializing={intelligenceRun.initializing} error={intelligenceRun.error} />
      <IntelligenceRunHistory runs={intelligenceRun.runs} latestRun={intelligenceRun.latestRun} selectedRun={intelligenceRun.run} onSelectCompleted={selectCompletedRun} />
    </section>
    {analysisError === "forbidden" ? <PermissionDeniedState /> : analysisError === "not_found" ? <NotFoundState /> : analysisError === "unavailable" ? <RetryableErrorState title="Claims unavailable" message="The selected completed analysis could not be loaded." onRetry={() => void loadAnalysis()} /> : selectedRunId ? <><div role="status" aria-live="polite" className="mt-5 rounded border border-hairline bg-surface p-3 text-sm text-text-muted">Showing claims and citations from the selected completed analysis. Run ID: <span className="font-mono text-xs">{selectedRunId}</span></div><ClaimExplanationPanel analysis={analysis} loadError={analysis ? null : "Loading selected completed analysis…"} citations={citations} selectedRunId={selectedRunId} canReview={canWrite} onReviewed={loadAnalysis} /></> : <EmptyState title={intelligenceRun.latestRun?.status === "FAILED" ? "No completed analysis selected" : "No completed analysis"} message={intelligenceRun.latestRun?.status === "FAILED" ? "The latest run failed; select an earlier completed analysis if one is available." : "Claims appear only after an analyst-requested run completes."} />}
  </main>;
}
