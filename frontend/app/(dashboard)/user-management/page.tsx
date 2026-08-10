"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";

interface OrgUser {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  role: { name: string; description: string };
}

const ROLE_OPTIONS = ["soc_analyst", "incident_responder", "security_architect", "ciso", "admin"] as const;

export default function UserManagementPage() {
  const [users, setUsers] = useState<OrgUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<OrgUser[]>("/api/v1/users");
      setUsers(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load users.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="font-display text-xl font-medium text-text-primary">User management</h1>
        <Button onClick={() => setInviteOpen((open) => !open)}>
          {inviteOpen ? "Cancel" : "Invite user"}
        </Button>
      </div>

      {inviteOpen && <InviteForm onInvited={() => { setInviteOpen(false); load(); }} />}

      {error && (
        <div className="mt-4 rounded border border-severity-critical/40 bg-severity-critical/10 px-3 py-2 text-sm text-severity-critical">
          {error}
        </div>
      )}

      <Card className="mt-4 p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hairline text-left text-xs text-text-muted">
              <th className="px-4 py-3 font-normal">Name</th>
              <th className="px-4 py-3 font-normal">Email</th>
              <th className="px-4 py-3 font-normal">Role</th>
              <th className="px-4 py-3 font-normal">Status</th>
            </tr>
          </thead>
          <tbody>
            {users === null && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-text-muted">
                  Loading…
                </td>
              </tr>
            )}
            {users?.map((user) => (
              <tr key={user.id} className="border-b border-hairline last:border-0">
                <td className="px-4 py-3 text-text-primary">{user.full_name}</td>
                <td className="px-4 py-3 font-mono text-xs text-text-muted">{user.email}</td>
                <td className="px-4 py-3 text-text-muted">{user.role.name.replace("_", " ")}</td>
                <td className="px-4 py-3">
                  <span
                    className={
                      user.is_active
                        ? "text-signal"
                        : "text-text-muted"
                    }
                  >
                    {user.is_active ? "Active" : "Deactivated"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function InviteForm({ onInvited }: { onInvited: () => void }) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<string>(ROLE_OPTIONS[0]);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await apiFetch("/api/v1/users", {
        method: "POST",
        body: JSON.stringify({ email, full_name: fullName, role_name: role }),
      });
      onInvited();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't invite user.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-4 rounded-card border border-hairline bg-surface p-4">
      {error && (
        <div className="mb-3 rounded border border-severity-critical/40 bg-severity-critical/10 px-3 py-2 text-sm text-severity-critical">
          {error}
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Input
          type="email"
          placeholder="name@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Input
          type="text"
          placeholder="Full name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          required
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="rounded border border-hairline bg-surface-raised px-3 py-2 text-sm text-text-primary"
        >
          {ROLE_OPTIONS.map((r) => (
            <option key={r} value={r}>
              {r.replace("_", " ")}
            </option>
          ))}
        </select>
      </div>
      <Button type="submit" className="mt-3" disabled={isSubmitting}>
        {isSubmitting ? "Inviting…" : "Send invite"}
      </Button>
    </form>
  );
}
