import { Card } from "@/components/ui/card";
import type { IntelligenceRun } from "@/lib/intelligence-run-client";
import { safeFailureCategory } from "@/lib/use-investigation-intelligence-run";

export function IntelligenceRunProgress({ run, submitting, initializing, error }: { run: IntelligenceRun | null; submitting: boolean; initializing: boolean; error: string | null }) {
  if (submitting) return <p role="status" aria-live="polite" className="mb-3 flex items-center gap-2 text-sm text-text-muted"><span aria-hidden="true" className="inline-block size-3 animate-spin rounded-full border-2 border-signal border-t-transparent" />Submitting analysis…</p>;
  if (initializing || !run) return error ? <Card role="alert" className="mb-3"><p className="text-sm text-text-muted">{error}</p></Card> : null;
  if (run.status === "QUEUED") return <p role="status" aria-live="polite" className="mb-3 text-sm text-text-muted">Analysis queued</p>;
  if (run.status === "RUNNING") return <p role="status" aria-live="polite" className="mb-3 flex items-center gap-2 text-sm text-text-muted"><span aria-hidden="true" className="inline-block size-3 animate-spin rounded-full border-2 border-signal border-t-transparent" />Aegis AI is analyzing the evidence</p>;
  if (run.status === "COMPLETED") return <p role="status" aria-live="polite" className="mb-3 text-sm text-signal">Analysis completed</p>;
  if (run.status === "FAILED") return <Card role="alert" className="mb-3"><p className="text-sm text-text-muted">Analysis failed: {safeFailureCategory(run)}</p></Card>;
  return <p role="status" aria-live="polite" className="mb-3 text-sm text-text-muted">Analysis cancelled</p>;
}
