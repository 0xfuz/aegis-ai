"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api-client";
import {
  createIntelligenceRunRequestKey,
  fetchIntelligenceRun,
  isActiveIntelligenceRun,
  listIntelligenceRuns,
  queueIntelligenceRun,
  type IntelligenceRun,
} from "@/lib/intelligence-run-client";
import { isInvestigationRouteId } from "@/lib/reconstruction-client";

const POLL_INTERVAL_MS = 3_000;
const SAFE_FAILURE_CATEGORIES = new Set([
  "EXECUTOR_UNAVAILABLE", "EXECUTOR_VALIDATION_FAILED", "EXECUTION_FAILED", "EXECUTION_ATTEMPTS_EXHAUSTED",
  "PROVIDER_DISABLED", "PROVIDER_MISCONFIGURED", "PROVIDER_UNAVAILABLE", "PROVIDER_MODEL_UNAVAILABLE",
  "PROVIDER_TIMEOUT", "PROVIDER_RESPONSE_TOO_LARGE", "PROVIDER_PROTOCOL_ERROR", "PROVIDER_CANCELLED",
  "PROVIDER_CONCURRENCY_LIMIT", "PROMPT_CONTEXT_INVALID", "PROMPT_TOO_LARGE", "CANDIDATE_MALFORMED_JSON",
  "CANDIDATE_SCHEMA_INVALID", "CANDIDATE_UNSUPPORTED_TYPE", "CANDIDATE_ALIAS_INVALID", "CANDIDATE_ROLE_INVALID",
  "CANDIDATE_RELATION_INVALID", "CANDIDATE_DUPLICATE", "CANDIDATE_SECRET_DETECTED", "CANDIDATE_TOO_LARGE",
]);

function errorMessage(error: unknown): string {
  const status = error instanceof ApiError ? error.status : (error as { status?: unknown })?.status;
  if (status === 403) return "You do not have permission to view this Intelligence Run.";
  if (status === 404) return "Intelligence Run not found.";
  return "Unable to refresh Intelligence Run status. Try again.";
}

export function safeFailureCategory(run: IntelligenceRun): string {
  return run.error_summary && SAFE_FAILURE_CATEGORIES.has(run.error_summary) ? run.error_summary : "EXECUTION_FAILED";
}

export function useInvestigationIntelligenceRun(
  investigationId: unknown,
  onCompleted: () => void | Promise<void>,
  requestedCompletedRunId?: string | null,
) {
  const [run, setRun] = useState<IntelligenceRun | null>(null);
  const [runs, setRuns] = useState<IntelligenceRun[]>([]);
  const [latestRun, setLatestRun] = useState<IntelligenceRun | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSequence = useRef(0);
  const completedRun = useRef<string | null>(null);
  const submissionInFlight = useRef(false);

  const notifyCompletion = useCallback((next: IntelligenceRun) => {
    if (next.status !== "COMPLETED" || completedRun.current === next.id) return;
    completedRun.current = next.id;
    void onCompleted();
  }, [onCompleted]);

  useEffect(() => {
    const sequence = ++requestSequence.current;
    const controller = new AbortController();
    completedRun.current = null;
    if (!isInvestigationRouteId(investigationId)) {
      setRun(null);
      setInitializing(false);
      setError("The Investigation identifier is invalid.");
      return () => controller.abort();
    }
    setInitializing(true);
    setError(null);
    void listIntelligenceRuns(investigationId, { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted || sequence !== requestSequence.current) return;
        const active = result.items.find((candidate) => isActiveIntelligenceRun(candidate)) ?? null;
        const completed = requestedCompletedRunId
          ? result.items.find((candidate) => candidate.id === requestedCompletedRunId && candidate.status === "COMPLETED") ?? null
          : result.items.find((candidate) => candidate.status === "COMPLETED") ?? null;
        setRuns(result.items);
        setLatestRun(result.items[0] ?? null);
        setRun(requestedCompletedRunId ? completed : active ?? completed);
        if (requestedCompletedRunId && !completed) setError("The selected completed analysis is unavailable.");
        setInitializing(false);
      })
      .catch((nextError: unknown) => {
        if (controller.signal.aborted || sequence !== requestSequence.current) return;
        setRun(null);
        setRuns([]);
        setLatestRun(null);
        setInitializing(false);
        setError(errorMessage(nextError));
      });
    return () => controller.abort();
  }, [investigationId, requestedCompletedRunId]);

  useEffect(() => {
    const activeRun = run;
    if (!isInvestigationRouteId(investigationId) || !activeRun || !isActiveIntelligenceRun(activeRun)) return;
    const controller = new AbortController();
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const next = await fetchIntelligenceRun(investigationId, activeRun.id, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setRun(next);
        setLatestRun((current) => current?.id === next.id ? next : current);
        setRuns((current) => current.map((candidate) => candidate.id === next.id ? next : candidate));
        setError(null);
        notifyCompletion(next);
        if (isActiveIntelligenceRun(next)) timeout = setTimeout(() => void poll(), POLL_INTERVAL_MS);
      } catch (nextError: unknown) {
        if (controller.signal.aborted) return;
        setError(errorMessage(nextError));
      }
    };
    timeout = setTimeout(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      if (timeout) clearTimeout(timeout);
    };
  }, [investigationId, notifyCompletion, run]);

  const submit = useCallback(async () => {
    if (!isInvestigationRouteId(investigationId) || submissionInFlight.current || submitting || initializing || isActiveIntelligenceRun(run)) return;
    submissionInFlight.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const queued = await queueIntelligenceRun(investigationId, createIntelligenceRunRequestKey());
      setRun(queued);
      setLatestRun(queued);
      setRuns((current) => [queued, ...current.filter((candidate) => candidate.id !== queued.id)]);
    } catch (nextError: unknown) {
      setError(errorMessage(nextError));
    } finally {
      submissionInFlight.current = false;
      setSubmitting(false);
    }
  }, [initializing, investigationId, run, submitting]);

  return {
    run,
    runs,
    latestRun,
    error,
    initializing,
    submitting,
    active: runs.some((candidate) => isActiveIntelligenceRun(candidate)),
    selectCompletedRun: (runId: string) => {
      const selected = runs.find((candidate) => candidate.id === runId && candidate.status === "COMPLETED");
      if (selected) setRun(selected);
    },
    submit,
  };
}

export { POLL_INTERVAL_MS };
