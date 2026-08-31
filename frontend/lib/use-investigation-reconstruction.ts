"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api-client";
import { fetchInvestigationReconstruction, isInvestigationRouteId, type InvestigationReconstruction } from "@/lib/reconstruction-client";

export type ReconstructionLoadState =
  | { status: "idle" | "loading"; data: null; error: null }
  | { status: "ready"; data: InvestigationReconstruction; error: null }
  | { status: "invalid" | "forbidden" | "not_found" | "error"; data: null; error: string };

const initialState: ReconstructionLoadState = { status: "idle", data: null, error: null };

export function useInvestigationReconstruction(investigationId: unknown, runId?: string | null) {
  const [state, setState] = useState<ReconstructionLoadState>(initialState);
  const [retryNonce, setRetryNonce] = useState(0);
  const requestSequence = useRef(0);

  useEffect(() => {
    const sequence = ++requestSequence.current;
    const controller = new AbortController();
    if (!isInvestigationRouteId(investigationId)) {
      setState({ status: "invalid", data: null, error: "The Investigation identifier is invalid." });
      return () => controller.abort();
    }

    setState({ status: "loading", data: null, error: null });
    void fetchInvestigationReconstruction(investigationId, { signal: controller.signal, runId })
      .then((data) => {
        if (!controller.signal.aborted && sequence === requestSequence.current) {
          setState({ status: "ready", data, error: null });
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || sequence !== requestSequence.current) return;
        if (error instanceof ApiError && error.status === 403) {
          setState({ status: "forbidden", data: null, error: "You do not have permission to view this reconstruction." });
        } else if (error instanceof ApiError && error.status === 404) {
          setState({ status: "not_found", data: null, error: "Investigation not found." });
        } else {
          setState({ status: "error", data: null, error: "Unable to load the certified reconstruction." });
        }
      });

    return () => controller.abort();
  }, [investigationId, retryNonce, runId]);

  const retry = useCallback(() => setRetryNonce((value) => value + 1), []);
  return { ...state, retry };
}
