import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api-client";
import { POLL_INTERVAL_MS, useInvestigationIntelligenceRun } from "@/lib/use-investigation-intelligence-run";
import type { IntelligenceRun } from "@/lib/intelligence-run-client";
import { IntelligenceRunProgress } from "@/components/investigations/intelligence-run-progress";

const apiFetch = vi.hoisted(() => vi.fn());
const reconstruction = vi.hoisted(() => vi.fn());
const auth = vi.hoisted(() => ({ canWrite: true, active: true }));

vi.mock("@/lib/api-client", async () => {
  class MockApiError extends Error {
    constructor(message: string, public status: number) { super(message); }
  }
  return { apiFetch, ApiError: MockApiError };
});
vi.mock("@/lib/reconstruction-client", () => ({ isInvestigationRouteId: (value: unknown) => typeof value === "string" && value.trim().length > 0, fetchInvestigationReconstruction: reconstruction }));
vi.mock("next/navigation", () => ({ useParams: () => ({ id: "case-42" }) }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ user: { is_active: auth.active }, hasPermission: () => auth.canWrite }) }));

const run = (status: IntelligenceRun["status"], error_summary: string | null = null): IntelligenceRun => ({
  id: "run-1", investigation_id: "case-42", status, request_key: "ui:test", input_hash: "hash", predecessor_analysis_id: null,
  context_version: "context-v1", builder_version: "builder-v1", prompt_template_version: "prompt-v1", output_schema_version: "schema-v1",
  generated_at: null, created_at: "2026-08-15T00:00:00Z", updated_at: "2026-08-15T00:00:00Z", error_summary,
});

function Probe({ id = "case-42", onCompleted = vi.fn() }: { id?: string; onCompleted?: () => void }) {
  const state = useInvestigationIntelligenceRun(id, onCompleted);
  return <><button onClick={() => void state.submit()} disabled={state.initializing || state.submitting || state.active}>Run analysis</button><span data-testid="run-status">{state.run?.status ?? "NONE"}</span><span data-testid="run-error">{state.error ?? ""}</span></>;
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("Intelligence Run progress", () => {
  it("renders accessible submit, queued, running, completed, failed and cancelled states without fake progress", () => {
    const { rerender } = render(<IntelligenceRunProgress run={null} submitting initializing={false} error={null} />);
    expect(screen.queryByText(/%/)).toBeNull();
    rerender(<IntelligenceRunProgress run={null} submitting={true} initializing={false} error={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Submitting analysis…");
    rerender(<IntelligenceRunProgress run={run("QUEUED")} submitting={false} initializing={false} error={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Analysis queued");
    rerender(<IntelligenceRunProgress run={run("RUNNING")} submitting={false} initializing={false} error={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Aegis AI is analyzing the evidence");
    rerender(<IntelligenceRunProgress run={run("COMPLETED")} submitting={false} initializing={false} error={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Analysis completed");
    rerender(<IntelligenceRunProgress run={run("FAILED", "PROVIDER_TIMEOUT")} submitting={false} initializing={false} error={null} />);
    expect(screen.getByRole("alert")).toHaveTextContent("PROVIDER_TIMEOUT");
    rerender(<IntelligenceRunProgress run={run("CANCELLED")} submitting={false} initializing={false} error={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Analysis cancelled");
  });

  it("recovers an active run after refresh, polls only it, refreshes on completion, and stops on terminal status", async () => {
    vi.useFakeTimers();
    const completed = vi.fn();
    apiFetch.mockResolvedValueOnce({ items: [run("RUNNING")], limit: 20, offset: 0 }).mockResolvedValueOnce(run("COMPLETED"));
    render(<Probe onCompleted={completed} />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId("run-status")).toHaveTextContent("RUNNING");
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS); await Promise.resolve(); });
    expect(screen.getByTestId("run-status")).toHaveTextContent("COMPLETED");
    expect(completed).toHaveBeenCalledTimes(1);
    const callsAfterCompletion = apiFetch.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2); });
    expect(apiFetch).toHaveBeenCalledTimes(callsAfterCompletion);
  });

  it("prevents duplicate submission while submitting or active and aborts polling on unmount", async () => {
    vi.useFakeTimers();
    let resolvePoll: ((value: IntelligenceRun) => void) | undefined;
    apiFetch.mockResolvedValueOnce({ items: [], limit: 20, offset: 0 }).mockResolvedValueOnce(run("QUEUED")).mockImplementationOnce(() => new Promise((resolve) => { resolvePoll = resolve; }));
    const view = render(<Probe />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByRole("button", { name: "Run analysis" })).toBeEnabled();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Run analysis" })); fireEvent.click(screen.getByRole("button", { name: "Run analysis" })); await Promise.resolve(); });
    expect(screen.getByTestId("run-status")).toHaveTextContent("QUEUED");
    expect(apiFetch.mock.calls.filter(([path, options]) => String(path).endsWith("/intelligence/runs") && options?.method === "POST")).toHaveLength(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS); });
    const pollOptions = apiFetch.mock.calls.at(-1)?.[1] as { signal?: AbortSignal };
    view.unmount();
    expect(pollOptions.signal?.aborted).toBe(true);
    await act(async () => { resolvePoll?.(run("RUNNING")); });
  });

  it("keeps permission and not-found failures bounded and does not poll them", async () => {
    apiFetch.mockRejectedValueOnce(new ApiError("ignored", 403));
    render(<Probe />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId("run-error")).toHaveTextContent("permission");
    expect(apiFetch).toHaveBeenCalledTimes(1);
  });
});
