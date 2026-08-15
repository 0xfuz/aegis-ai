import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "@/components/layout/sidebar";

const state = vi.hoisted(() => ({ pathname: "/investigations", apiFetch: vi.fn(), permissions: ["investigation:read", "assets:read", "threat_intel:read"] }));
vi.mock("next/navigation", () => ({ usePathname: () => state.pathname }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: ReactNode }) => <a href={href} {...props}>{children}</a> }));
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ user: { full_name: "Analyst", role: { name: "analyst" } }, hasPermission: (permission: string) => state.permissions.includes(permission) }) }));
vi.mock("@/lib/api-client", () => ({ apiFetch: state.apiFetch }));

describe("sidebar navigation", () => {
  beforeEach(() => { state.apiFetch.mockResolvedValue({ open_investigations: 0 }); state.permissions = ["investigation:read", "assets:read", "threat_intel:read"]; });
  afterEach(cleanup);

  it("keeps the sidebar module-based and hides deferred intelligence links", () => {
    state.pathname = "/investigations";
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: "Cases" })).toHaveAttribute("href", "/investigations");
    for (const label of ["Analysis", "Hypotheses", "Reasoning", "Recommendations", "Overview", "Evidence", "Timeline", "Indicators", "Entities", "Attack Graph"]) expect(screen.queryByText(label)).toBeNull();
    expect(screen.getByText("Security / Platform")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Assets" })).toHaveAttribute("href", "/assets");
    for (const label of ["Reports", "Analytics", "Detections"]) expect(screen.queryByRole("link", { name: label })).toBeNull();
  });

  it("does not duplicate investigation workspace routes in the sidebar", () => {
    state.pathname = "/investigations/case-42/evidence";
    render(<Sidebar />);
    for (const label of ["Overview", "Evidence", "Timeline", "Indicators", "Entities", "Attack Graph"]) expect(screen.queryByRole("link", { name: label })).toBeNull();
  });

  it("only shows modules backed by the current user permissions", () => {
    state.permissions = ["investigation:read"];
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: "Cases" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Assets" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Threat Intelligence" })).toBeNull();
  });
});
