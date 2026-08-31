import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/login/page";

const search = vi.hoisted(() => ({ value: "" }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(search.value) }));
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ login: vi.fn() }) }));

afterEach(() => { cleanup(); vi.unstubAllEnvs(); search.value = ""; });

describe("production login presentation", () => {
  it("renders only the bounded password-change notice", () => {
    search.value = "message=password-changed";
    render(<LoginPage />);
    expect(screen.getByRole("status")).toHaveTextContent("Password changed successfully. Sign in again.");

    cleanup();
    search.value = "";
    render(<LoginPage />);
    expect(screen.queryByRole("status")).toBeNull();

    cleanup();
    search.value = "message=arbitrary";
    render(<LoginPage />);
    expect(screen.queryByRole("status")).toBeNull();
    expect(document.body.textContent).not.toContain("arbitrary");
  });
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
