"use client";

import { FormEvent, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't sign in. Try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="font-display text-2xl font-medium text-text-primary">Aegis AI</div>
          <p className="mt-1 text-sm text-text-muted">Sign in to your security decision engine</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-card border border-hairline bg-surface p-6"
        >
          {error && (
            <div className="mb-4 rounded border border-severity-critical/40 bg-severity-critical/10 px-3 py-2 text-sm text-severity-critical">
              {error}
            </div>
          )}

          <label className="mb-1 block text-xs text-text-muted" htmlFor="email">
            Email
          </label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="name@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="mb-4"
          />

          <label className="mb-1 block text-xs text-text-muted" htmlFor="password">
            Password
          </label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            placeholder="Enter your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="mb-6"
          />

          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-text-muted">
          Demo credentials: admin@aegis.demo / ChangeMe123!
        </p>
      </div>
    </div>
  );
}
