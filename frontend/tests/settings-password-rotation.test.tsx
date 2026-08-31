import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SettingsPage from "@/app/(dashboard)/settings/page";

const state = vi.hoisted(() => ({ api: vi.fn(), clear: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: state.replace }) }));
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    clearSession: () => {
      state.clear();
      localStorage.removeItem("aegis_access_token");
      localStorage.removeItem("aegis_refresh_token");
    },
  }),
}));
vi.mock("@/lib/api-client", () => ({
  apiFetch: state.api,
  ApiError: class ApiError extends Error {},
}));

const fill = (current: string, next: string, confirmation = next) => {
  fireEvent.change(screen.getByLabelText("Current password"), { target: { value: current } });
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: next } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: confirmation } });
};

beforeEach(() => {
  state.api.mockReset();
  state.api.mockResolvedValue([]);
  state.clear.mockReset();
  state.replace.mockReset();
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(cleanup);

describe("Settings password rotation", () => {
  it("renders password-only self-service controls with safe autocomplete", () => {
    render(<SettingsPage />);

    expect(screen.getByRole("heading", { name: "Security" })).toBeVisible();
    expect(screen.getByLabelText("Current password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByLabelText("New password")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByLabelText("Confirm new password")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.queryByText(/other user/i)).toBeNull();
  });

  it("rejects mismatch and invalid bounds without a rotation request", () => {
    render(<SettingsPage />);
    fill("Current-Password-42", "Short-42!", "Other-Password-42");
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(state.api).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert")).toHaveTextContent("do not match");

    fill("Current-Password-42", "short", "short");
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(state.api).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert")).toHaveTextContent("between 12 and 128");

    const tooLong = `A${"b".repeat(126)}1!`;
    fill("Current-Password-42", tooLong, tooLong);
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(state.api).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert")).toHaveTextContent("between 12 and 128");
  });

  it("posts only the current user payload then clears credentials and redirects", async () => {
    localStorage.setItem("aegis_access_token", "synthetic-session");
    localStorage.setItem("aegis_refresh_token", "synthetic-session");
    state.api.mockResolvedValueOnce([]).mockResolvedValueOnce(undefined);
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<SettingsPage />);
    fill("Current-Password-42", "New-Password-73!");
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));

    await waitFor(() => expect(state.api).toHaveBeenCalledWith("/api/v1/auth/password/rotate", {
      method: "POST",
      body: JSON.stringify({ current_password: "Current-Password-42", new_password: "New-Password-73!" }),
    }));
    expect(state.clear).toHaveBeenCalledOnce();
    expect(state.replace).toHaveBeenCalledWith("/login?message=password-changed");
    expect(state.replace.mock.calls.flat().join(" ")).not.toContain("Current-Password-42");
    expect(localStorage.getItem("aegis_access_token")).toBeNull();
    expect(localStorage.getItem("aegis_refresh_token")).toBeNull();
    expect(sessionStorage.length).toBe(0);
    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByLabelText("New password")).toHaveValue("");
    expect(screen.getByLabelText("Confirm new password")).toHaveValue("");
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("prevents duplicate rotation submissions while the request is pending", async () => {
    let resolveRotation: (() => void) | undefined;
    state.api.mockResolvedValueOnce([]).mockImplementationOnce(() => new Promise<void>((resolve) => { resolveRotation = resolve; }));
    render(<SettingsPage />);
    fill("Current-Password-42", "New-Password-73!");

    const submit = screen.getByRole("button", { name: "Change password" });
    fireEvent.click(submit);
    fireEvent.click(submit);
    expect(state.api).toHaveBeenCalledTimes(2);
    expect(submit).toBeDisabled();

    resolveRotation?.();
    await waitFor(() => expect(state.replace).toHaveBeenCalledWith("/login?message=password-changed"));
  });

  it("clears fields and presents only a generic error on failure", async () => {
    state.api.mockResolvedValueOnce([]).mockRejectedValueOnce(new Error("wrong"));
    render(<SettingsPage />);
    fill("Current-Password-42", "New-Password-73!");
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to change password");
    expect(screen.getByRole("alert")).not.toHaveTextContent("wrong");
    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByLabelText("New password")).toHaveValue("");
    expect(screen.getByLabelText("Confirm new password")).toHaveValue("");
  });
});
