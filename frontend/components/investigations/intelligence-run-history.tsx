import { Card } from "@/components/ui/card";
import { safeFailureCategory } from "@/lib/use-investigation-intelligence-run";
import type { IntelligenceRun } from "@/lib/intelligence-run-client";

export function IntelligenceRunHistory({ runs, latestRun, selectedRun, onSelectCompleted }: {
  runs: IntelligenceRun[];
  latestRun: IntelligenceRun | null;
  selectedRun: IntelligenceRun | null;
  onSelectCompleted: (runId: string) => void;
}) {
  if (runs.length === 0) return null;
  return <section className="mt-5" aria-labelledby="intelligence-run-history">
    <h2 id="intelligence-run-history" className="mb-2 text-base font-medium">Analysis run history</h2>
    <Card>
      {latestRun?.status === "FAILED" && <p role="status" className="text-sm text-text-muted">Latest run failed: {safeFailureCategory(latestRun)}. Earlier completed runs remain available for review.</p>}
      {selectedRun?.status === "COMPLETED" && <p role="status" className="mt-2 text-sm text-text-muted">Showing claims and citations for completed run {selectedRun.id}.</p>}
      <ol aria-label="Server-ordered Intelligence Run history" className="mt-3 space-y-2">
        {runs.map((candidate) => <li key={candidate.id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-hairline p-2 text-xs">
          <span><strong>{candidate.status}</strong> · {candidate.created_at}{candidate.error_summary ? ` · ${safeFailureCategory(candidate)}` : ""}</span>
          {candidate.status === "COMPLETED" ? <button type="button" className="rounded text-signal underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal" aria-pressed={selectedRun?.id === candidate.id} onClick={() => onSelectCompleted(candidate.id)}>View completed run</button> : <span>Run {candidate.id}</span>}
        </li>)}
      </ol>
    </Card>
  </section>;
}
