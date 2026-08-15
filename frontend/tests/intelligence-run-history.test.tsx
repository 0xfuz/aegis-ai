import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IntelligenceRunHistory } from "@/components/investigations/intelligence-run-history";
import type { IntelligenceRun } from "@/lib/intelligence-run-client";

const run = (id: string, status: IntelligenceRun["status"], error_summary: string | null = null): IntelligenceRun => ({
  id, investigation_id: "case-1", status, error_summary, request_key: "ui:test", input_hash: "hash", predecessor_analysis_id: null,
  context_version: "context", builder_version: "builder", prompt_template_version: "prompt", output_schema_version: "schema", generated_at: null,
  created_at: "2026-08-15T00:00:00Z", updated_at: "2026-08-15T00:00:00Z",
});

afterEach(cleanup);

describe("Intelligence Run history", () => {
  it("keeps the latest failed run visible while selecting only a completed run for review", () => {
    const select = vi.fn();
    const completed = run("completed-1", "COMPLETED");
    const failed = run("failed-1", "FAILED", "PROVIDER_TIMEOUT");
    render(<IntelligenceRunHistory runs={[failed, completed]} latestRun={failed} selectedRun={completed} onSelectCompleted={select} />);
    expect(screen.getAllByRole("status")[0]).toHaveTextContent("Latest run failed: PROVIDER_TIMEOUT");
    expect(screen.getByText("Showing claims and citations for completed run completed-1.")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Server-ordered Intelligence Run history" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View completed run" }));
    expect(select).toHaveBeenCalledWith("completed-1");
    expect(screen.queryByRole("button", { name: /failed-1/i })).toBeNull();
  });

  it("renders server-provided text as inert text and exposes selection state accessibly", () => {
    const completed = run("<b>completed</b>", "COMPLETED");
    const { container } = render(<IntelligenceRunHistory runs={[completed]} latestRun={completed} selectedRun={completed} onSelectCompleted={() => {}} />);
    expect(screen.getByText("Showing claims and citations for completed run <b>completed</b>.")).toBeInTheDocument();
    expect(container.querySelector("b")).toBeNull();
    expect(screen.getByRole("button", { name: "View completed run" })).toHaveAttribute("aria-pressed", "true");
  });
});
