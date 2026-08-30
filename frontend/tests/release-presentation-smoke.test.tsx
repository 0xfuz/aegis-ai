import { readFileSync } from "node:fs";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/login/page";
import { GET as healthz } from "@/app/healthz/route";
import { Sidebar } from "@/components/layout/sidebar";
import { WorkspaceNav } from "@/components/investigations/workspace-nav";

const state = vi.hoisted(() => ({ pathname: "/dashboard", permissions: ["investigation:read", "assets:read", "threat_intel:read"] }));

vi.mock("next/navigation", () => ({ usePathname: () => state.pathname, useSearchParams: () => new URLSearchParams() }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: ReactNode }) => <a href={href} {...props}>{children}</a> }));
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ user: { full_name: "Release administrator", role: { name: "admin" } }, hasPermission: (permission: string) => state.permissions.includes(permission) }) }));
vi.mock("@/lib/api-client", () => ({ apiFetch: vi.fn().mockResolvedValue({ open_investigations: 0 }) }));

afterEach(() => { cleanup(); vi.unstubAllEnvs(); });
beforeEach(() => { state.pathname = "/dashboard"; state.permissions = ["investigation:read", "assets:read", "threat_intel:read"]; });

describe("release presentation smoke", () => {
  it("keeps the public entry bounded and production login free of demo credentials", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "false");
    const response = healthz();
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "ok", service: "frontend" });
    render(<LoginPage />);
    expect(document.body.textContent).not.toMatch(/admin@aegis\.demo|ChangeMe123!|demo credentials/i);
  });

  it("renders only supported permission-aware primary navigation with visible focus styles", () => {
    render(<Sidebar />);
    for (const label of ["Dashboard", "Cases", "Alert Triage", "Assets", "Threat Intelligence", "Settings", "User management"]) expect(screen.getByRole("link", { name: label })).toBeVisible();
    for (const label of ["Detections", "Analytics", "Reports", "Attack Graph"]) expect(screen.queryByRole("link", { name: label })).toBeNull();
    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Cases" })).toHaveClass("focus-visible:outline");
  });

  it("keeps WorkspaceNav as the sole complete Investigation navigation and leaves completed pages non-placeholder", () => {
    render(<WorkspaceNav investigationId="case-1" />);
    const expected = [["Overview", "overview"], ["Evidence", "evidence"], ["Timeline", "timeline"], ["Indicators", "indicators"], ["Entities", "entities"], ["Attack Graph", "relationships"], ["Intelligence", "intelligence"], ["Findings", "findings"], ["MITRE ATT&CK", "mitre"], ["Notes", "notes"], ["Reports", "reports"], ["Audit Trail", "audit"]] as const;
    for (const [label, segment] of expected) expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", `/investigations/case-1/${segment}`);
    expect(screen.queryByRole("link", { name: "Attack Graph" })?.getAttribute("href")).not.toContain("/attack-graph");
    for (const page of ["notes", "reports", "audit"]) {
      const source = readFileSync(`app/(dashboard)/investigations/[id]/${page}/page.tsx`, "utf8");
      expect(source).not.toContain("CompatibilityPlaceholder");
    }
  });
});
