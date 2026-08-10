/**
 * Thin fetch wrapper around the Aegis AI backend. Handles attaching the
 * access token, and transparently retries once after refreshing on a 401 —
 * callers never need to think about token expiry.
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("aegis_access_token");
}

function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("aegis_refresh_token");
}

export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem("aegis_access_token", accessToken);
  localStorage.setItem("aegis_refresh_token", refreshToken);
}

export function clearTokens(): void {
  localStorage.removeItem("aegis_access_token");
  localStorage.removeItem("aegis_refresh_token");
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;

  const response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    clearTokens();
    return null;
  }

  const data = await response.json();
  setTokens(data.access_token, data.refresh_token);
  return data.access_token as string;
}

export async function downloadFile(path: string): Promise<void> {
  const token = getAccessToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(body?.error?.message ?? body?.detail ?? "Couldn't generate that file.", response.status);
  }

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="(.+)"/);
  const filename = match?.[1] ?? "download";

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

interface RequestOptions extends RequestInit {
  skipAuth?: boolean;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { skipAuth, headers, ...rest } = options;

  const doFetch = async (token: string | null): Promise<Response> => {
    const isFormData = typeof FormData !== "undefined" && rest.body instanceof FormData;
    return fetch(`${API_BASE_URL}${path}`, {
      ...rest,
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...(token && !skipAuth ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
    });
  };

  let response = await doFetch(getAccessToken());

  if (response.status === 401 && !skipAuth) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      response = await doFetch(newToken);
    }
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(body?.error?.message ?? body?.detail ?? "Request failed", response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
