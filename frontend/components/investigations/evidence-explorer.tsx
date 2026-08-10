"use client";

import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";

export interface EvidenceRecord {
  id: string;
  category: string;
  occurred_at: string;
  summary: string;
  details: Record<string, unknown>;
}

const CATEGORY_LABELS: Record<string, string> = {
  process: "Processes",
  file: "Files",
  registry: "Registry",
  dns: "DNS",
  firewall: "Firewall",
  authentication: "Authentication",
  network_connection: "Network",
  powershell: "PowerShell",
  command_history: "Command history",
  browser_history: "Browser history",
};

// Fixed display order — categories a SOC analyst thinks of roughly in
// this sequence (identity/access first, then execution, then artifacts
// left behind), rather than whatever order they happen to appear in data.
const CATEGORY_ORDER = [
  "authentication",
  "network_connection",
  "dns",
  "firewall",
  "process",
  "powershell",
  "command_history",
  "file",
  "registry",
  "browser_history",
];

export function EvidenceExplorer({ records }: { records: EvidenceRecord[] }) {
  const [activeCategory, setActiveCategory] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<EvidenceRecord | null>(null);

  const presentCategories = useMemo(() => {
    const present = new Set(records.map((r) => r.category));
    return CATEGORY_ORDER.filter((c) => present.has(c));
  }, [records]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return records.filter((r) => {
      if (activeCategory !== "all" && r.category !== activeCategory) return false;
      if (!q) return true;
      const haystack = `${r.summary} ${JSON.stringify(r.details)}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [records, activeCategory, query]);

  if (records.length === 0) {
    return (
      <div>
        <div className="mb-2 text-xs text-text-muted">Evidence explorer</div>
        <div className="rounded border border-hairline px-3 py-4 text-center text-xs text-text-muted">
          No forensic evidence recorded for this investigation yet.
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs text-text-muted">Evidence explorer</span>
        <span className="text-[11px] text-text-muted">
          {filtered.length} of {records.length}
        </span>
      </div>

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search evidence…"
        className="mb-2 w-full rounded border border-hairline bg-surface-raised px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-muted"
      />

      <div className="mb-3 flex flex-wrap gap-1.5">
        <button
          onClick={() => setActiveCategory("all")}
          className={cn(
            "rounded-full px-2 py-0.5 text-[11px] transition-colors",
            activeCategory === "all" ? "bg-signal/20 text-signal" : "bg-surface-raised text-text-muted hover:text-text-primary",
          )}
        >
          All
        </button>
        {presentCategories.map((category) => (
          <button
            key={category}
            onClick={() => setActiveCategory(category)}
            className={cn(
              "rounded-full px-2 py-0.5 text-[11px] transition-colors",
              activeCategory === category
                ? "bg-signal/20 text-signal"
                : "bg-surface-raised text-text-muted hover:text-text-primary",
            )}
          >
            {CATEGORY_LABELS[category] ?? category}
          </button>
        ))}
      </div>

      <div className="max-h-64 space-y-1 overflow-y-auto">
        {filtered.map((record) => (
          <button
            key={record.id}
            onClick={() => setSelected(record)}
            className="block w-full rounded border border-hairline px-2.5 py-1.5 text-left text-xs hover:bg-surface-raised"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="rounded bg-surface-raised px-1.5 py-0.5 text-[10px] text-text-muted">
                {CATEGORY_LABELS[record.category] ?? record.category}
              </span>
              <span className="text-[10px] text-text-muted">
                {new Date(record.occurred_at).toLocaleTimeString()}
              </span>
            </div>
            <div className="mt-1 text-text-primary">{record.summary}</div>
          </button>
        ))}
        {filtered.length === 0 && (
          <div className="py-4 text-center text-xs text-text-muted">No evidence matches that search.</div>
        )}
      </div>

      {selected && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          onClick={() => setSelected(null)}
        >
          <div
            className="w-full max-w-md rounded-card border border-hairline bg-surface p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between">
              <span className="rounded bg-surface-raised px-1.5 py-0.5 text-[10px] text-text-muted">
                {CATEGORY_LABELS[selected.category] ?? selected.category}
              </span>
              <button onClick={() => setSelected(null)} className="text-text-muted hover:text-text-primary">
                ✕
              </button>
            </div>
            <div className="mt-2 text-sm text-text-primary">{selected.summary}</div>
            <div className="mt-1 text-xs text-text-muted">{new Date(selected.occurred_at).toLocaleString()}</div>

            <dl className="mt-4 space-y-2 text-xs">
              {Object.entries(selected.details).map(([key, value]) => (
                <div key={key} className="flex justify-between gap-4 border-b border-hairline pb-2 last:border-0">
                  <dt className="shrink-0 capitalize text-text-muted">{key.replace(/_/g, " ")}</dt>
                  <dd className="break-all text-right font-mono text-text-primary">{String(value)}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      )}
    </div>
  );
}
