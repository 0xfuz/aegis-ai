import { describe, expect, it, vi } from "vitest";

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api-client", () => ({ apiFetch }));

import { fetchIntelligenceAnalysis, fetchIntelligenceRun, listIntelligenceRuns, queueIntelligenceRun } from "@/lib/intelligence-run-client";

describe("Intelligence Run client", () => {
  it("uses only canonical, encoded run endpoints", async () => {
    apiFetch.mockResolvedValue({});
    await queueIntelligenceRun("case / 42", "ui:key");
    await fetchIntelligenceRun("case / 42", "run / 1");
    await listIntelligenceRuns("case / 42");
    await fetchIntelligenceAnalysis("case / 42", "run / 1");
    expect(apiFetch).toHaveBeenNthCalledWith(1, "/api/v1/investigations/case%20%2F%2042/intelligence/runs", expect.objectContaining({ method: "POST", body: JSON.stringify({ request_key: "ui:key" }) }));
    expect(apiFetch).toHaveBeenNthCalledWith(2, "/api/v1/investigations/case%20%2F%2042/intelligence/runs/run%20%2F%201", {});
    expect(apiFetch).toHaveBeenNthCalledWith(3, "/api/v1/investigations/case%20%2F%2042/intelligence/runs?limit=20&offset=0", {});
    expect(apiFetch).toHaveBeenNthCalledWith(4, "/api/v1/investigations/case%20%2F%2042/intelligence?run_id=run%20%2F%201", {});
    expect(apiFetch.mock.calls.some(([path]) => String(path).endsWith("/analyze"))).toBe(false);
  });

  it("rejects malformed route identifiers before requesting", async () => {
    apiFetch.mockClear();
    expect(() => listIntelligenceRuns(" ")).toThrow("Investigation ID");
    await expect(fetchIntelligenceRun("case-42", "")).rejects.toThrow("Run ID");
    expect(apiFetch).not.toHaveBeenCalled();
  });
});
