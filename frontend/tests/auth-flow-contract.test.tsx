import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "@/lib/auth-context";

const routerPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush }),
}));

function AuthProbe() {
  const { clearSession, isLoading, login, user } = useAuth();
  const [error, setError] = useState<string | null>(null);
  return (
    <section>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="principal">{user ? "authenticated" : "anonymous"}</span>
      <span data-testid="error">{error ?? "none"}</span>
      <button onClick={() => { void login("operator@example.invalid", "synthetic-password").catch(() => setError("failed")); }}>
        Sign in
      </button>
      <button onClick={clearSession}>Clear session</button>
    </section>
  );
}

const currentLoginResponse = {
  access_token: "synthetic-access-token",
  refresh_token: "synthetic-refresh-token",
  token_type: "bearer",
  expires_in: 900,
  password_rotation_required: false,
};

const currentPrincipal = {
  id: "user-safe-id",
  org_id: "org-safe-id",
  email: "operator@example.invalid",
  full_name: "Release Operator",
  is_active: true,
  role: { id: "role-safe-id", name: "admin", description: "Administrator", permissions: ["investigation:read"] },
};

describe("production login response contract", () => {
  beforeEach(() => {
    localStorage.clear();
    routerPush.mockReset();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("accepts the current login response shape, establishes the existing session, and loads the authenticated principal", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(currentLoginResponse), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(currentPrincipal), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    render(<AuthProvider><AuthProbe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(screen.getByTestId("principal")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("error")).toHaveTextContent("none");
    expect(routerPush).toHaveBeenCalledWith("/dashboard");
    expect(fetchMock.mock.calls[0]![0]).toBe("http://localhost:8000/api/v1/auth/login");
    expect(fetchMock.mock.calls[1]![0]).toBe("http://localhost:8000/api/v1/auth/me");
    expect((fetchMock.mock.calls[1]![1] as RequestInit).headers).toMatchObject({ Authorization: "Bearer synthetic-access-token" });
    expect(localStorage.getItem("aegis_access_token")).not.toBeNull();
    expect(document.body.textContent).not.toContain(currentLoginResponse.access_token);
    expect(document.body.textContent).not.toContain(currentLoginResponse.refresh_token);
  });

  it("keeps a rejected login bounded and does not establish a session", async () => {
    const rejectedLogin = new Response(
      JSON.stringify({ detail: "Incorrect email or password." }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    );
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(rejectedLogin));
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Sign in" })); });
    await waitFor(() => expect(screen.getByTestId("error")).toHaveTextContent("failed"));
    expect(screen.getByTestId("principal")).toHaveTextContent("anonymous");
    expect(localStorage.getItem("aegis_access_token")).toBeNull();
    expect(routerPush).not.toHaveBeenCalled();
  });

  it("clears the in-memory principal and browser credentials without another auth request", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(currentLoginResponse), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(currentPrincipal), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(screen.getByTestId("principal")).toHaveTextContent("authenticated"));

    fireEvent.click(screen.getByRole("button", { name: "Clear session" }));
    expect(screen.getByTestId("principal")).toHaveTextContent("anonymous");
    expect(localStorage.getItem("aegis_access_token")).toBeNull();
    expect(localStorage.getItem("aegis_refresh_token")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
