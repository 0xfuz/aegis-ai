import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceNav } from "@/components/investigations/workspace-nav";

vi.mock("next/navigation", () => ({ usePathname: () => "/investigations/case-1/evidence" }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a> }));

describe("investigation workspace navigation", () => {
  it("provides factual workspace routes and retains the legacy entry point", () => {
    render(<WorkspaceNav investigationId="case-1" />);
    expect(screen.getByRole("navigation", { name: "Investigation workspace" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Evidence" })).toHaveAttribute("href", "/investigations/case-1/evidence");
    expect(screen.getByRole("link", { name: "Reports" })).toHaveAttribute("href", "/investigations/case-1/reports");
    expect(screen.getByRole("link", { name: "Legacy view" })).toHaveAttribute("href", "/investigations/case-1");
  });
});
