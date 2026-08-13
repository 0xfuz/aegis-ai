import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, setTokens } from "@/lib/api-client";
import { fetchInvestigationReconstruction, type InvestigationReconstruction } from "@/lib/reconstruction-client";
import { useInvestigationReconstruction } from "@/lib/use-investigation-reconstruction";

const response: InvestigationReconstruction = {
  policy_id: "reconstruction-read-v1", investigation: { id: "case-2", title: "Case", status: "new" }, versions: { context: "phase8-context-v1", activity: "activity-window-v1", gaps: "reconstruction-gaps-v1" },
  context: { warnings: [], omissions: [], section_counts: {} }, activity: { policy_id: "activity-window-v1", anchor: null, activities: [], omitted: 0, warnings: ["ANCHOR_MISSING"] },
  gaps: { policy_id: "reconstruction-gaps-v1", gaps: [], omitted: 0 }, sections: { evidence: [], raw_records: [], events: [], entity_observations: [], indicator_occurrences: [], relationships: [], citations: [], findings: [], mitre: [] }, pagination: { section_omissions: {}, total_omitted: 0 }, warnings: [],
};

function Probe({ id }: { id: unknown }) {
  const state = useInvestigationReconstruction(id);
  return <><span data-testid="status">{state.status}</span><span data-testid="case">{state.data?.investigation.id ?? "none"}</span><button onClick={state.retry}>retry</button></>;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe("typed reconstruction API client", () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("uses only the encoded certified GET endpoint without authority or policy fields", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(response), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await fetchInvestigationReconstruction("case /2");
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/investigations/case%20%2F2/intelligence/reconstruction");
    expect(options.body).toBeUndefined();
    expect(url).not.toMatch(/org_id|actor|snapshot|policy|alias|max_bytes|target/);
  });

  it("keeps the existing single-refresh 401 behavior", async () => {
    setTokens("old-access", "refresh-token");
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "new-access", refresh_token: "new-refresh" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(response), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(fetchInvestigationReconstruction("case-2")).resolves.toEqual(response);
    expect(fetchMock.mock.calls[1]![0]).toBe("http://localhost:8000/api/v1/auth/refresh");
    expect((fetchMock.mock.calls[2]![1] as RequestInit).headers).toMatchObject({ Authorization: "Bearer new-access" });
  });

  it("rejects a missing route identifier without a request", async () => {
    const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
    await expect(fetchInvestigationReconstruction(" ")).rejects.toThrow("Investigation ID");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("route-scoped reconstruction loader", () => {
  beforeEach(() => { cleanup(); vi.restoreAllMocks(); });
  afterEach(() => cleanup());

  it.each([[403, "forbidden"], [404, "not_found"]] as const)("keeps HTTP %s distinguishable as %s", async (status, expected) => {
    vi.spyOn(await import("@/lib/reconstruction-client"), "fetchInvestigationReconstruction").mockRejectedValue(new ApiError("hidden", status));
    render(<Probe id="case-2" />);
    expect(await screen.findByTestId("status")).toHaveTextContent(expected);
  });

  it("retries a bounded generic failure without retaining prior case state", async () => {
    const client = await import("@/lib/reconstruction-client");
    vi.spyOn(client, "fetchInvestigationReconstruction").mockRejectedValueOnce(new ApiError("network", 500)).mockResolvedValueOnce(response);
    render(<Probe id="case-2" />);
    expect(await screen.findByTestId("status")).toHaveTextContent("error");
    expect(screen.getByTestId("case")).toHaveTextContent("none");
    fireEvent.click(screen.getByRole("button", { name: "retry" }));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    expect(screen.getByTestId("case")).toHaveTextContent("case-2");
    expect(client.fetchInvestigationReconstruction).toHaveBeenCalledTimes(2);
  });

  it("discards stale route results and aborts the prior request", async () => {
    const client = await import("@/lib/reconstruction-client");
    const first = deferred<InvestigationReconstruction>(); const second = deferred<InvestigationReconstruction>();
    const fetchMock = vi.spyOn(client, "fetchInvestigationReconstruction").mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const view = render(<Probe id="case-1" />);
    const firstSignal = (fetchMock.mock.calls[0]![1] as { signal: AbortSignal }).signal;
    view.rerender(<Probe id="case-2" />);
    expect(firstSignal.aborted).toBe(true);
    await act(async () => { second.resolve(response); });
    await waitFor(() => expect(screen.getByTestId("case")).toHaveTextContent("case-2"));
    await act(async () => { first.resolve({ ...response, investigation: { ...response.investigation, id: "case-1" } }); });
    expect(screen.getByTestId("case")).toHaveTextContent("case-2");
    const currentSignal = (fetchMock.mock.calls[1]![1] as { signal: AbortSignal }).signal;
    view.unmount();
    expect(currentSignal.aborted).toBe(true);
  });

  it("does not request malformed route IDs", async () => {
    const client = await import("@/lib/reconstruction-client");
    const fetchMock = vi.spyOn(client, "fetchInvestigationReconstruction");
    render(<Probe id={undefined} />);
    expect(await screen.findByTestId("status")).toHaveTextContent("invalid");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
