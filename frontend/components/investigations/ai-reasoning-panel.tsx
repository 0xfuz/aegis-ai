"use client";

import { ConfidenceRing } from "@/components/ui/confidence-ring";
import { cn } from "@/lib/utils";

interface AttackChainStep {
  phase: string;
  description: string;
}

interface AlternativeHypothesis {
  hypothesis: string;
  likelihood: number;
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

interface AIReasoningPanelProps {
  confidence: number;
  rootCause: string;
  mitreTechniques: string[];
  blastRadiusSummary: string;
  falsePositiveProbability: number;
  attackChain: AttackChainStep[];
  alternativeHypotheses: AlternativeHypothesis[];
  reasoningChain: string[];
  recommendedActions: RecommendedAction[];
  isAnalyzing: boolean;
  onAnalyze: () => void;
  onDecideAction: (actionId: string, approve: boolean) => void;
}

const IMPACT_STYLES: Record<string, string> = {
  low: "bg-signal/15 text-signal",
  medium: "bg-severity-medium/15 text-severity-medium",
  high: "bg-severity-critical/15 text-severity-critical",
};

export function AIReasoningPanel({
  confidence,
  rootCause,
  mitreTechniques,
  blastRadiusSummary,
  falsePositiveProbability,
  attackChain,
  alternativeHypotheses,
  reasoningChain,
  recommendedActions,
  isAnalyzing,
  onAnalyze,
  onDecideAction,
}: AIReasoningPanelProps) {
  const unanalyzed = confidence === 0;

  return (
    <div className="rounded-card border border-cognition/30 bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs text-cognition">Aegis reasoning</span>
        {unanalyzed && (
          <button
            onClick={onAnalyze}
            disabled={isAnalyzing}
            className="rounded bg-cognition/20 px-2 py-1 text-[11px] text-cognition hover:bg-cognition/30 disabled:opacity-50"
          >
            {isAnalyzing ? "Analyzing…" : "Analyze with Aegis AI"}
          </button>
        )}
      </div>

      {unanalyzed ? (
        <p className="text-xs text-text-muted">Not yet analyzed.</p>
      ) : (
        <>
          <div className="mb-3 flex items-start justify-between gap-2">
            <span className="text-xs text-text-muted">Root cause</span>
            <ConfidenceRing value={confidence} />
          </div>
          <p className="mb-4 text-xs text-text-primary">{rootCause}</p>

          {attackChain.length > 0 && (
            <div className="mb-4">
              <div className="mb-1.5 text-xs text-text-muted">Attack chain</div>
              <div className="space-y-1.5">
                {attackChain.map((step, i) => (
                  <div key={i} className="flex gap-2 text-xs">
                    <div className="flex flex-col items-center">
                      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-cognition/20 text-[9px] text-cognition">
                        {i + 1}
                      </span>
                      {i < attackChain.length - 1 && <span className="mt-0.5 h-full w-px bg-hairline" />}
                    </div>
                    <div className="pb-2">
                      <div className="font-medium text-text-primary">{step.phase}</div>
                      <div className="text-text-muted">{step.description}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="mb-1 text-xs text-text-muted">MITRE mapping</div>
          <p className="mb-4 font-mono text-xs text-text-primary">{mitreTechniques.join(", ") || "None identified"}</p>

          <div className="mb-1 text-xs text-text-muted">Blast radius</div>
          <p className="mb-4 text-xs text-text-primary">{blastRadiusSummary}</p>

          <div className="mb-1 text-xs text-text-muted">False-positive probability</div>
          <p className="mb-4 text-xs text-text-primary">{falsePositiveProbability}%</p>

          {reasoningChain.length > 0 && (
            <div className="mb-4">
              <div className="mb-1.5 text-xs text-text-muted">Reasoning trace</div>
              <ol className="space-y-1 text-xs text-text-primary">
                {reasoningChain.map((step, i) => (
                  <li key={i} className="flex gap-1.5">
                    <span className="text-text-muted">{i + 1}.</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {alternativeHypotheses.length > 0 && (
            <div className="mb-4">
              <div className="mb-1.5 text-xs text-text-muted">Alternative hypotheses considered</div>
              <div className="space-y-1.5">
                {alternativeHypotheses.map((h, i) => (
                  <div key={i} className="text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-text-primary">{h.hypothesis}</span>
                      <span className="text-text-muted">{h.likelihood}%</span>
                    </div>
                    <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-surface-raised">
                      <div className="h-full bg-text-muted/50" style={{ width: `${h.likelihood}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="mb-2 text-xs text-text-muted">Recommended actions</div>
          <div className="space-y-2">
            {recommendedActions.map((action) => (
              <div key={action.id} className="rounded bg-surface-raised p-2.5">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-text-primary">{action.title}</span>
                  {action.confidence !== null && <ConfidenceRing value={action.confidence} size={24} />}
                </div>
                <div className="mt-0.5 text-[11px] text-text-muted">{action.description}</div>

                <div className="mt-2 flex flex-wrap gap-1.5">
                  {action.business_impact && (
                    <span
                      className={cn(
                        "rounded-full px-1.5 py-0.5 text-[10px] capitalize",
                        IMPACT_STYLES[action.business_impact] ?? "bg-surface text-text-muted",
                      )}
                    >
                      {action.business_impact} impact
                    </span>
                  )}
                  {action.estimated_time_to_contain && (
                    <span className="rounded-full bg-surface px-1.5 py-0.5 text-[10px] text-text-muted">
                      ETA {action.estimated_time_to_contain}
                    </span>
                  )}
                  {action.approval_tier && (
                    <span className="rounded-full bg-surface px-1.5 py-0.5 text-[10px] text-text-muted">
                      Needs {action.approval_tier}
                    </span>
                  )}
                </div>

                {(action.side_effects || action.rollback) && (
                  <div className="mt-2 space-y-1 border-t border-hairline pt-2 text-[10px]">
                    {action.side_effects && (
                      <div>
                        <span className="text-text-muted">Side effects: </span>
                        <span className="text-text-primary">{action.side_effects}</span>
                      </div>
                    )}
                    {action.rollback && (
                      <div>
                        <span className="text-text-muted">Rollback: </span>
                        <span className="text-text-primary">{action.rollback}</span>
                      </div>
                    )}
                  </div>
                )}

                {action.status === "pending" ? (
                  <div className="mt-2 flex gap-2">
                    <button
                      onClick={() => onDecideAction(action.id, true)}
                      className="rounded bg-signal/20 px-2 py-1 text-[11px] text-signal hover:bg-signal/30"
                    >
                      Approve &amp; execute
                    </button>
                    <button
                      onClick={() => onDecideAction(action.id, false)}
                      className="rounded px-2 py-1 text-[11px] text-text-muted hover:text-text-primary"
                    >
                      Dismiss
                    </button>
                  </div>
                ) : (
                  <div className="mt-2 text-[11px] capitalize text-text-muted">{action.status}</div>
                )}
              </div>
            ))}
            {recommendedActions.length === 0 && <div className="text-xs text-text-muted">No actions recommended.</div>}
          </div>
        </>
      )}
    </div>
  );
}
