import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/login/page";

vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ login: vi.fn() }) }));

afterEach(() => { cleanup(); vi.unstubAllEnvs(); });

describe("production login presentation", () => {
  it("does not render demo credentials when the demo flag is absent or false", () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "false");
    render(<LoginPage />);
    expect(screen.queryByText(/demo credentials/i)).toBeNull();
    expect(document.body.textContent).not.toContain("admin@aegis.demo");
    expect(document.body.textContent).not.toContain("ChangeMe123!");
  });

  it("shows only a non-sensitive local-demo indicator when explicitly enabled", () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "true");
    render(<LoginPage />);
    expect(screen.getByText(/local demo mode is enabled/i)).toBeVisible();
    expect(document.body.textContent).not.toContain("admin@aegis.demo");
    expect(document.body.textContent).not.toContain("ChangeMe123!");
  });
});
