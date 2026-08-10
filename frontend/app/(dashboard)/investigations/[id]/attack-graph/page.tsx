"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api-client";
import { AttackGraphView } from "@/components/attack-graph/attack-graph-view";
import type { AttackGraphData } from "@/components/attack-graph/types";

export default function InvestigationAttackGraphPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [graph, setGraph] = useState<AttackGraphData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<AttackGraphData>(`/api/v1/investigations/${id}/attack-graph`)
      .then(setGraph)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load the attack graph."));
  }, [id]);

  return (
    <div className="flex h-[calc(100vh-6rem)] flex-col">
      <button
        onClick={() => router.push(`/investigations/${id}`)}
        className="mb-3 self-start text-sm text-text-muted hover:text-text-primary"
      >
        ← Back to investigation
      </button>

      {error && (
        <div className="mb-3 rounded border border-severity-critical/40 bg-severity-critical/10 px-3 py-2 text-sm text-severity-critical">
          {error}
        </div>
      )}

      {!graph && !error && <div className="text-sm text-text-muted">Building attack graph…</div>}

      {graph && (
        <div className="flex-1 overflow-hidden rounded-card border border-hairline bg-surface">
          <AttackGraphView graph={graph} />
        </div>
      )}
    </div>
  );
}
