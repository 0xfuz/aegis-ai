"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api-client";
import { clearTokens } from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CopyButton } from "@/components/ui/copy-button";

interface Connector {
  id: string;
  name: string;
  type: string;
  status: string;
  is_active: boolean;
  last_event_at: string | null;
  created_at: string;
}

interface ConnectorCreated {
  connector: Connector;
  ingest_url: string;
  ingest_secret: string;
}

function buildCurlCommand(created: ConnectorCreated): string {
  return `curl -X POST ${created.ingest_url} \\
  -H "Content-Type: application/json" \\
  -H "X-Ingest-Secret: ${created.ingest_secret}" \\
  -d '{"title":"Test event","severity":"medium","description":"Sent from curl","indicators":[{"type":"ip","value":"203.0.113.5"}]}'`;
}

export default function SettingsPage() {
  const router = useRouter();
  const [connectors, setConnectors] = useState<Connector[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nameInput, setNameInput] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [justCreated, setJustCreated] = useState<ConnectorCreated | null>(null);
  const [currentPassword, setCurrentPassword] = useState(""); const [newPassword, setNewPassword] = useState(""); const [confirmPassword, setConfirmPassword] = useState(""); const [rotating, setRotating] = useState(false); const [rotationError, setRotationError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<Connector[]>("/api/v1/connectors");
      setConnectors(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load connectors.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!nameInput.trim()) return;
    setIsCreating(true);
    setError(null);
    try {
      const result = await apiFetch<ConnectorCreated>("/api/v1/connectors/webhook", {
        method: "POST",
        body: JSON.stringify({ name: nameInput }),
      });
      setJustCreated(result);
      setNameInput("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create connector.");
    } finally {
      setIsCreating(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await apiFetch(`/api/v1/connectors/${id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't remove connector.");
    }
  }

  async function rotatePassword(event: React.FormEvent) {
    event.preventDefault();
    if (rotating) return;
    if (newPassword !== confirmPassword) { setRotationError("New passwords do not match."); setCurrentPassword(""); setNewPassword(""); setConfirmPassword(""); return; }
    if (newPassword.length < 12 || newPassword.length > 128) { setRotationError("Use a password between 12 and 128 characters."); setCurrentPassword(""); setNewPassword(""); setConfirmPassword(""); return; }
    setRotating(true); setRotationError(null);
    try { await apiFetch("/api/v1/auth/password/rotate", { method: "POST", body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) }); clearTokens(); setCurrentPassword(""); setNewPassword(""); setConfirmPassword(""); router.replace("/login?message=password-changed"); }
    catch { setRotationError("Unable to change password. Check your current password and try again."); setCurrentPassword(""); setNewPassword(""); setConfirmPassword(""); }
    finally { setRotating(false); }
  }

  return (
    <div>
      <h1 className="font-display text-xl font-medium text-text-primary">Settings</h1>
      <p className="mt-1 text-sm text-text-muted">
        Connectors turn external events into real investigations — no mock data involved.
        Vendor-specific connectors (Sentinel, Splunk, Elastic, CrowdStrike, cloud audit logs) land
        as the same pattern in later phases; this webhook connector is the first real one.
      </p>

      {error && (
        <div className="mt-4 rounded border border-severity-critical/40 bg-severity-critical/10 px-3 py-2 text-sm text-severity-critical">
          {error}
        </div>
      )}

      <section aria-labelledby="security-settings" className="mt-6"><h2 id="security-settings" className="font-display text-lg text-text-primary">Security</h2><p className="mt-1 text-sm text-text-muted">Change your own password. Use 12–128 characters with upper-case, lower-case, number, and symbol strength; server validation remains authoritative.</p><form onSubmit={rotatePassword} className="mt-3 max-w-md space-y-3"><label className="block text-sm">Current password<Input aria-label="Current password" type="password" autoComplete="current-password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} required /></label><label className="block text-sm">New password<Input aria-label="New password" type="password" autoComplete="new-password" value={newPassword} onChange={event => setNewPassword(event.target.value)} required minLength={12} maxLength={128} /></label><label className="block text-sm">Confirm new password<Input aria-label="Confirm new password" type="password" autoComplete="new-password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} required minLength={12} maxLength={128} /></label>{rotationError && <p role="alert" className="text-sm text-severity-critical">{rotationError}</p>}<Button type="submit" disabled={rotating || !currentPassword || !newPassword || !confirmPassword}>{rotating ? "Changing password…" : "Change password"}</Button></form></section>

      {justCreated && (
        <div className="mt-4 rounded-card border border-cognition/40 bg-cognition/5 p-4">
          <div className="mb-2 text-sm text-text-primary">
            <strong>{justCreated.connector.name}</strong> created. Save this secret now — it won&apos;t be shown again.
          </div>
          <div className="mb-1 flex items-center justify-between">
            <span className="text-xs text-text-muted">Ingest URL</span>
            <CopyButton text={justCreated.ingest_url} />
          </div>
          <div className="mb-3 break-all rounded bg-surface-raised p-2 font-mono text-xs text-text-primary">
            {justCreated.ingest_url}
          </div>
          <div className="mb-1 flex items-center justify-between">
            <span className="text-xs text-text-muted">Secret (send as the X-Ingest-Secret header)</span>
            <CopyButton text={justCreated.ingest_secret} />
          </div>
          <div className="mb-3 break-all rounded bg-surface-raised p-2 font-mono text-xs text-text-primary">
            {justCreated.ingest_secret}
          </div>
          <div className="mb-1 flex items-center justify-between">
            <span className="text-xs text-text-muted">Try it</span>
            <CopyButton text={buildCurlCommand(justCreated)} />
          </div>
          <pre className="overflow-x-auto rounded bg-surface-raised p-2 font-mono text-[11px] text-text-primary">
            {buildCurlCommand(justCreated)}
          </pre>
          <Button variant="secondary" className="mt-3" onClick={() => setJustCreated(null)}>
            Done
          </Button>
        </div>
      )}

      <form onSubmit={handleCreate} className="mt-4 flex gap-2">
        <Input
          placeholder="Connector name, e.g. 'CI pipeline alerts'"
          value={nameInput}
          onChange={(e) => setNameInput(e.target.value)}
        />
        <Button type="submit" disabled={isCreating || !nameInput.trim()}>
          {isCreating ? "Creating…" : "Add webhook connector"}
        </Button>
      </form>

      <Card className="mt-4 p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hairline text-left text-xs text-text-muted">
              <th className="px-4 py-3 font-normal">Name</th>
              <th className="px-4 py-3 font-normal">Type</th>
              <th className="px-4 py-3 font-normal">Status</th>
              <th className="px-4 py-3 font-normal">Last event</th>
              <th className="px-4 py-3 font-normal"></th>
            </tr>
          </thead>
          <tbody>
            {connectors === null && !error && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-text-muted">
                  Loading…
                </td>
              </tr>
            )}
            {connectors?.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-text-muted">
                  No connectors yet — add one above.
                </td>
              </tr>
            )}
            {connectors?.map((c) => (
              <tr key={c.id} className="border-b border-hairline last:border-0">
                <td className="px-4 py-3 text-text-primary">{c.name}</td>
                <td className="px-4 py-3 capitalize text-text-muted">{c.type}</td>
                <td className="px-4 py-3">
                  <span className={c.status === "connected" ? "text-signal" : "text-severity-critical"}>
                    {c.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-text-muted">
                  {c.last_event_at ? new Date(c.last_event_at).toLocaleString() : "Never"}
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => handleDelete(c.id)}
                    className="text-xs text-text-muted hover:text-severity-critical"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
