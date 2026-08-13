"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import type { IntelligenceClaim } from "@/components/investigations/claim-citation-explanation";

type ReviewDecision = "CONFIRMED" | "REJECTED" | "UNRESOLVED";

const transitions: Record<IntelligenceClaim["review_status"], ReviewDecision[]> = {
  PENDING: ["CONFIRMED", "REJECTED", "UNRESOLVED"],
  UNRESOLVED: ["CONFIRMED", "REJECTED"],
  CONFIRMED: [],
  REJECTED: [],
  SUPERSEDED: [],
};

function safeReviewError(error: unknown): "forbidden" | "not_found" | "error" {
  if (error instanceof ApiError && error.status === 403) return "forbidden";
  if (error instanceof ApiError && error.status === 404) return "not_found";
  return "error";
}

export function ClaimReviewControls({ claim, canReview, onReviewed }: {
  claim: IntelligenceClaim;
  canReview: boolean;
  onReviewed: () => Promise<void>;
}) {
  const [decision, setDecision] = useState<ReviewDecision | null>(null);
  const [rationale, setRationale] = useState("");
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState<"saved" | "forbidden" | "not_found" | "error" | null>(null);
  const [denied, setDenied] = useState(false);
  const requestRef = useRef<AbortController | null>(null);
  const actionRefs = useRef<Partial<Record<ReviewDecision, HTMLButtonElement | null>>>({});

  const allowed = transitions[claim.review_status];
  useEffect(() => () => requestRef.current?.abort(), [claim.id]);

  function returnFocus(target: ReviewDecision | null) {
    if (target) requestAnimationFrame(() => actionRefs.current[target]?.focus());
  }

  function cancel() {
    const previous = decision;
    setDecision(null);
    setRationale("");
    returnFocus(previous);
  }

  async function submit() {
    if (!decision || pending) return;
    const selected = decision;
    const controller = new AbortController();
    requestRef.current?.abort();
    requestRef.current = controller;
    setPending(true);
    setFeedback(null);
    try {
      await apiFetch(`/api/v1/investigations/intelligence/items/${encodeURIComponent(claim.id)}/review`, {
        method: "POST",
        body: JSON.stringify({ status: selected, rationale: rationale.trim() }),
        signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        await onReviewed();
        setDecision(null);
        setRationale("");
        setFeedback("saved");
        returnFocus(selected);
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        const outcome = safeReviewError(error);
        setFeedback(outcome);
        if (outcome === "forbidden") setDenied(true);
      }
    } finally {
      if (!controller.signal.aborted) setPending(false);
    }
  }

  if (!canReview || allowed.length === 0) return null;
  const rejecting = decision === "REJECTED";
  return <div className="mt-3 border-t border-hairline pt-3" aria-label={`Review controls for ${claim.claim_type} claim`}>
    <p className="text-xs text-text-muted">Review changes only this claim’s status. Type, origin, and statement remain immutable.</p>
    {feedback === "saved" && <p role="status" aria-live="polite" className="mt-2 text-xs text-signal">Review saved. Authoritative claim status refreshed.</p>}
    {feedback === "forbidden" && <p role="alert" className="mt-2 text-xs text-text-muted">You do not have permission to review this claim.</p>}
    {feedback === "not_found" && <p role="alert" className="mt-2 text-xs text-text-muted">This claim is no longer available for review.</p>}
    {feedback === "error" && <p role="alert" className="mt-2 text-xs text-text-muted">Review could not be saved. You can retry without creating a duplicate review.</p>}
    <div className="mt-2 flex flex-wrap gap-2">
      {!denied && allowed.map((status) => <Button key={status} variant={status === "REJECTED" ? "secondary" : "primary"} disabled={pending || feedback === "saved"} ref={(element) => { actionRefs.current[status] = element; }} onClick={() => { setFeedback(null); setDecision(status); }} aria-label={`Review ${claim.claim_type} claim as ${status}`}>
        Mark {status[0] + status.slice(1).toLowerCase()}
      </Button>)}
    </div>
    {decision && <div role="alertdialog" aria-modal="true" aria-labelledby={`review-title-${claim.id}`} className="mt-3 rounded border border-hairline p-3">
      <h3 id={`review-title-${claim.id}`} className="text-sm font-medium">Confirm {decision[0] + decision.slice(1).toLowerCase()} review</h3>
      <p className="mt-1 text-xs text-text-muted">Current: {claim.claim_type} · {claim.origin} · {claim.review_status}. This updates only review status.</p>
      <label className="mt-3 block text-xs" htmlFor={`review-rationale-${claim.id}`}>{rejecting ? "Rejection rationale (required)" : "Review rationale (optional)"}</label>
      <textarea id={`review-rationale-${claim.id}`} value={rationale} maxLength={500} disabled={pending} onChange={(event) => setRationale(event.target.value)} className="mt-1 min-h-16 w-full rounded border border-hairline bg-surface px-2 py-1 text-sm" />
      <div className="mt-3 flex gap-2"><Button disabled={pending || (rejecting && !rationale.trim())} onClick={() => void submit()} aria-label={`Confirm ${decision} review for ${claim.claim_type} claim`}>{pending ? "Saving…" : `Confirm ${decision[0] + decision.slice(1).toLowerCase()}`}</Button><Button variant="secondary" disabled={pending} onClick={cancel}>Cancel</Button></div>
    </div>}
  </div>;
}
