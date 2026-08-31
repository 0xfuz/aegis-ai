"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, clearTokens, setTokens } from "@/lib/api-client";

export interface CurrentUser {
  id: string;
  org_id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  role: {
    id: string;
    name: string;
    description: string;
    permissions: string[];
  };
}

interface AuthContextValue {
  user: CurrentUser | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  clearSession: () => void;
  hasPermission: (code: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  const loadCurrentUser = useCallback(async () => {
    try {
      const me = await apiFetch<CurrentUser>("/api/v1/auth/me");
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const hasToken = typeof window !== "undefined" && localStorage.getItem("aegis_access_token");
    if (hasToken) {
      loadCurrentUser();
    } else {
      setIsLoading(false);
    }
  }, [loadCurrentUser]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await apiFetch<{ access_token: string; refresh_token: string }>(
        "/api/v1/auth/login",
        {
          method: "POST",
          skipAuth: true,
          body: JSON.stringify({ email, password }),
        },
      );
      setTokens(tokens.access_token, tokens.refresh_token);
      await loadCurrentUser();
      router.push("/dashboard");
    },
    [loadCurrentUser, router],
  );

  const clearSession = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = typeof window !== "undefined" ? localStorage.getItem("aegis_refresh_token") : null;
    if (refreshToken) {
      await apiFetch("/api/v1/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refreshToken }),
      }).catch(() => {
        // Logout is best-effort client-side regardless of API result —
        // tokens are cleared locally either way.
      });
    }
    clearSession();
    router.push("/login");
  }, [clearSession, router]);

  const hasPermission = useCallback(
    (code: string) => Boolean(user?.role.permissions.includes(code)),
    [user],
  );

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, clearSession, hasPermission }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
