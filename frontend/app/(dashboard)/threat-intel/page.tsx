"use client";

import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { VerdictBadge } from "@/components/ui/verdict-badge";
import { IOCDetailOverlay } from "@/components/investigations/ioc-detail";

interface IOCSummary {
  type: string;
  value: string;
  tags: string[];
  confidence: number;
  verdict: string;
  provenance: string;
  is_watched: boolean;
  sightings_count: number;
  last_seen: string;
}

const INDICATOR_TYPES = ["ip", "hash", "domain", "url", "asset"] as const;
const VERDICT_FILTERS = ["all", "malicious", "suspicious", "unknown", "benign"] as const;
type VerdictFilter = (typeof VERDICT_FILTERS)[number];
type ViewTab = "all" | "watchlist";

export default function ThreatIntelPage() {
  const [tab, setTab] = useState<ViewTab>("all");
  const [verdictFilter, setVerdictFilter] = useState<VerdictFilter>("all");
  const [iocs, setIocs] = useState<IOCSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [searchType, setSearchType] = useState<string>(INDICATOR_TYPES[0]);
  const [searchValue, setSearchValue] = useState("");
  const [selected, setSelected] = useState<{ type: string; value: string } | null>(null);

  function load() {
    setIocs(null);
    setError(null);
    const params = new URLSearchParams();
    if (verdictFilter !== "all") params.set("verdict", verdictFilter);
    const path =
      tab === "watchlist"
        ? "/api/v1/investigations/iocs/watchlist"
        : `/api/v1/investigations/iocs${params.toString() ? `?${params.toString()}` : ""}`;
    apiFetch<IOCSummary[]>(path)
      .then(setIocs)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load indicators."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, verdictFilter]);

  // Closing the detail overlay may have changed watch state — refresh the
  // list so the table/watchlist reflects it without a full page reload.
  function handleOverlayClose() {
    setSelected(null);
    load();
  }

  const filtered =
    iocs?.filter((i) => {
      if (verdictFilter !== "all" && i.verdict !== verdictFilter) return false;
      return i.value.toLowerCase().includes(query.toLowerCase());
    }) ?? null;

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchValue.trim()) return;
    setSelected({ type: searchType, value: searchValue.trim() });
  }

  return (
    <div>
      <h1 className="font-display text-xl font-medium text-text-primary">Threat intelligence</h1>
      <p className="mt-1 text-sm text-text-muted">
        Every indicator ever recorded across your investigations and connectors, with confidence, verdict,
        provenance, sightings, and real cross-investigation relationships — no simulated feed data.
      </p>

      {error && (
        <div className="mt-4 rounded border border-severity-critical/40 bg-severity-critical/10 px-3 py-2 text-sm text-severity-critical">
          {error}
        </div>
      )}

      <form onSubmit={handleSearch} className="mt-4 flex gap-2">
        <select
          value={searchType}
          onChange={(e) => setSearchType(e.target.value)}
          className="rounded border border-hairline bg-surface-raised px-3 py-2 text-sm text-text-primary"
        >
          {INDICATOR_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <Input
          placeholder="Look up any IP, hash, domain, URL, or asset — even ones not seen yet"
          value={searchValue}
          onChange={(e) => setSearchValue(e.target.value)}
        />
        <Button type="submit" disabled={!searchValue.trim()}>
          Look up
        </Button>
      </form>

      <div className="mt-6 flex items-center gap-1 border-b border-hairline">
        <button
          onClick={() => setTab("all")}
          className={
            "px-3 py-2 text-sm " +
            (tab === "all"
              ? "border-b-2 border-signal text-text-primary"
              : "text-text-muted hover:text-text-primary")
          }
        >
          All indicators
        </button>
        <button
          onClick={() => setTab("watchlist")}
          className={
            "px-3 py-2 text-sm " +
            (tab === "watchlist"
              ? "border-b-2 border-signal text-text-primary"
              : "text-text-muted hover:text-text-primary")
          }
        >
          ★ Watchlist
        </button>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5">
          {VERDICT_FILTERS.map((v) => (
            <button
              key={v}
              onClick={() => setVerdictFilter(v)}
              className={
                "rounded-full px-3 py-1 text-xs capitalize " +
                (verdictFilter === v
                  ? "bg-signal text-void"
                  : "border border-hairline text-text-muted hover:text-text-primary")
              }
            >
              {v}
            </button>
          ))}
        </div>
        <Input
          placeholder="Filter…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-56"
        />
      </div>

      <Card className="mt-2 p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hairline text-left text-xs text-text-muted">
              <th className="px-4 py-3 font-normal"></th>
              <th className="px-4 py-3 font-normal">Value</th>
              <th className="px-4 py-3 font-normal">Type</th>
              <th className="px-4 py-3 font-normal">Verdict</th>
              <th className="px-4 py-3 font-normal">Tags</th>
              <th className="px-4 py-3 font-normal">Confidence</th>
              <th className="px-4 py-3 font-normal">Sightings</th>
              <th className="px-4 py-3 font-normal">Last seen</th>
            </tr>
          </thead>
          <tbody>
            {iocs === null && !error && (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-text-muted">
                  Loading…
                </td>
              </tr>
            )}
            {filtered?.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-text-muted">
                  {tab === "watchlist"
                    ? iocs?.length === 0
                      ? "Nothing on the watchlist yet — open any indicator below and add it."
                      : "No watchlisted indicators match that filter."
                    : iocs?.length === 0
                      ? "No indicators recorded yet — they appear automatically from investigations and connectors."
                      : "No indicators match that filter."}
                </td>
              </tr>
            )}
            {filtered?.map((ioc) => (
              <tr
                key={`${ioc.type}:${ioc.value}`}
                onClick={() => setSelected({ type: ioc.type, value: ioc.value })}
                className="cursor-pointer border-b border-hairline last:border-0 hover:bg-surface-raised"
              >
                <td className="px-2 py-3 text-center text-text-muted">{ioc.is_watched ? "★" : ""}</td>
                <td className="px-4 py-3 font-mono text-text-primary">{ioc.value}</td>
                <td className="px-4 py-3 uppercase text-text-muted">{ioc.type}</td>
                <td className="px-4 py-3">
                  <VerdictBadge verdict={ioc.verdict} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {ioc.tags.map((tag) => (
                      <span key={tag} className="rounded-full bg-severity-critical/15 px-2 py-0.5 text-[10px] text-severity-critical">
                        {tag}
                      </span>
                    ))}
                    {ioc.tags.length === 0 && <span className="text-xs text-text-muted">—</span>}
                  </div>
                </td>
                <td className="px-4 py-3 text-text-primary">{ioc.confidence}%</td>
                <td className="px-4 py-3 text-text-primary">{ioc.sightings_count}</td>
                <td className="px-4 py-3 text-text-muted">{new Date(ioc.last_seen).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {selected && (
        <IOCDetailOverlay
          type={selected.type}
          value={selected.value}
          onClose={handleOverlayClose}
        />
      )}
    </div>
  );
}
