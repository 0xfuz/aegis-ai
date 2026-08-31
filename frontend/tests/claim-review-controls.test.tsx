import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api-client";
import { ClaimReviewControls } from "@/components/investigations/claim-review-controls";
import type { IntelligenceClaim } from "@/components/investigations/claim-citation-explanation";

const state = vi.hoisted(() => ({ apiFetch: vi.fn(), reviewed: vi.fn() }));
vi.mock("@/lib/api-client", async () => ({ ...(await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client")), apiFetch: state.apiFetch }));

const pending: IntelligenceClaim = { id: "claim safe/id", kind: "OBSERVATION", claim_type: "OBSERVATION", origin: "AI", statement: "<img src=x onerror=alert(1)>", confidence: 52, review_status: "PENDING", fact_links: [] };
function renderControls(claim = pending, canReview = true) {
  return render(<ClaimReviewControls claim={claim} canReview={canReview} onReviewed={state.reviewed} />);
}

describe("claim review controls", () => {
  beforeEach(() => { state.apiFetch.mockReset().mockResolvedValue({ id: pending.id, review_status: "CONFIRMED" }); state.reviewed.mockReset().mockResolvedValue(undefined); });
  afterEach(() => cleanup());

  it("exposes only canonical allowed transitions and no supersession control", () => {
    const { rerender } = renderControls();
    expect(screen.getByRole("button", { name: "Review OBSERVATION claim as CONFIRMED" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review OBSERVATION claim as REJECTED" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review OBSERVATION claim as UNRESOLVED" })).toBeInTheDocument();
    expect(screen.queryByText(/Supersed/i)).toBeNull();
    rerender(<ClaimReviewControls claim={{ ...pending, review_status: "UNRESOLVED" }} canReview onReviewed={state.reviewed} />);
    expect(screen.getByRole("button", { name: "Review OBSERVATION claim as CONFIRMED" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review OBSERVATION claim as REJECTED" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /UNRESOLVED/ })).toBeNull();
    rerender(<ClaimReviewControls claim={{ ...pending, review_status: "SUPERSEDED" }} canReview onReviewed={state.reviewed} />);
    expect(screen.queryByLabelText(/Review controls/)).toBeNull();
  });

  it("requires an explicit, keyboard-operable confirmation and refreshes authoritative state", async () => {
    renderControls();
    const trigger = screen.getByRole("button", { name: "Review OBSERVATION claim as CONFIRMED" });
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Current: OBSERVATION · AI · PENDING");
    fireEvent.click(screen.getByRole("button", { name: "Confirm CONFIRMED review for OBSERVATION claim" }));
    await waitFor(() => expect(state.apiFetch).toHaveBeenCalledWith("/api/v1/investigations/intelligence/items/claim%20safe%2Fid/review", expect.objectContaining({ method: "POST", body: JSON.stringify({ status: "CONFIRMED", rationale: "" }) })));
    await waitFor(() => expect(state.reviewed).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("status")).toHaveTextContent("Authoritative claim status refreshed");
  });

  it("requires rationale for rejection, prevents duplicates, and returns focus on cancellation", async () => {
    renderControls();
    const trigger = screen.getByRole("button", { name: "Review OBSERVATION claim as REJECTED" });
    fireEvent.click(trigger);
    const confirm = screen.getByRole("button", { name: "Confirm REJECTED review for OBSERVATION claim" });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Rejection rationale (required)"), { target: { value: "Not supported by available evidence" } });
    fireEvent.click(screen.getByText("Cancel"));
    await waitFor(() => expect(document.activeElement).toBe(trigger));
    fireEvent.click(trigger);
    fireEvent.change(screen.getByLabelText("Rejection rationale (required)"), { target: { value: "Not supported by available evidence" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm REJECTED review for OBSERVATION claim" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm REJECTED review for OBSERVATION claim" }));
    await waitFor(() => expect(state.apiFetch).toHaveBeenCalledTimes(1));
  });

  it("keeps read-only analysts passive and uses a safe 403 state", async () => {
    const { rerender } = renderControls(pending, false);
    expect(screen.queryByRole("button", { name: /Review OBSERVATION/ })).toBeNull();
    rerender(<ClaimReviewControls claim={pending} canReview onReviewed={state.reviewed} />);
    fireEvent.click(screen.getByRole("button", { name: "Review OBSERVATION claim as CONFIRMED" }));
    state.apiFetch.mockRejectedValueOnce(new ApiError("secret backend detail", 403));
    fireEvent.click(screen.getByRole("button", { name: "Confirm CONFIRMED review for OBSERVATION claim" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("do not have permission");
    expect(screen.queryByText("secret backend detail")).toBeNull();
    expect(screen.queryByRole("button", { name: /Review OBSERVATION/ })).toBeNull();
  });

  it("keeps 404 anti-enumeration-safe and retryable failures retryable", async () => {
    const { unmount } = renderControls();
    state.apiFetch.mockRejectedValueOnce(new ApiError("missing", 404));
    fireEvent.click(screen.getByRole("button", { name: "Review OBSERVATION claim as CONFIRMED" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm CONFIRMED review for OBSERVATION claim" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("no longer available");
    unmount();
    renderControls();
    state.apiFetch.mockRejectedValueOnce(new Error("network"));
    fireEvent.click(screen.getByRole("button", { name: "Review OBSERVATION claim as CONFIRMED" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm CONFIRMED review for OBSERVATION claim" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You can retry");
  });
});
