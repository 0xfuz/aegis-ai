"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { SeverityBadge } from "@/components/ui/severity-badge";

interface Asset {
  id: string;
  name: string;
  asset_type: string;
  os: string | null;
  owner: string | null;
  department: string | null;
  criticality: string;
  health: string;
  risk_score: number;
  last_seen: string;
}

interface RelatedInvestigation {
  id: string;
  title: string;
  severity: string;
  status: string;
}

interface AssetDetail extends Asset {
  open_vulnerabilities: { cve?: string; severity?: string }[];
  installed_software: string[];
  running_services: string[];
  security_controls: string[];
  cloud_tags: Record<string, string>;
  ai_risk_summary: string | null;
  related_investigations: RelatedInvestigation[];
}

const CRITICALITY_STYLES: Record<string, string> = {
  critical: "bg-severity-critical/15 text-severity-critical",
  high: "bg-severity-high/15 text-severity-high",
  medium: "bg-severity-medium/15 text-severity-medium",
  low: "bg-severity-low/15 text-severity-low",
};

const HEALTH_STYLES: Record<string, string> = {
  compromised: "text-severity-critical",
  at_risk: "text-severity-high",
  healthy: "text-signal",
  unknown: "text-text-muted",
};

export default function AssetsPage() {
  const searchParams = useSearchParams();
  const [assets, setAssets] = useState<Asset[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<AssetDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Asset[]>("/api/v1/assets")
      .then(setAssets)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load assets."));
  }, []);

  function openAsset(id: string) {
    setDetailError(null);
    apiFetch<AssetDetail>(`/api/v1/assets/${id}`)
      .then(setSelected)
      .catch((err) => setDetailError(err instanceof ApiError ? err.message : "Couldn't load asset detail."));
  }

  // Deep-linked from elsewhere (e.g. an Attack Graph asset node) via
  // /assets?assetId=... — opens straight to that asset's detail.
  useEffect(() => {
    const assetId = searchParams.get("assetId");
    if (assetId) openAsset(assetId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  return (
    <div>
      <h1 className="font-display text-xl font-medium text-text-primary">Assets</h1>
      <p className="mt-1 text-sm text-text-muted">
        Populated from investigations that reference them — risk score and criticality are curated per
        asset, not invented per view.
      </p>

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
              <th className="px-4 py-3 font-normal">Owner</th>
              <th className="px-4 py-3 font-normal">Criticality</th>
              <th className="px-4 py-3 font-normal">Health</th>
              <th className="px-4 py-3 font-normal">Risk score</th>
              <th className="px-4 py-3 font-normal">Last seen</th>
            </tr>
          </thead>
          <tbody>
            {assets === null && !error && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-text-muted">
                  Loading…
                </td>
              </tr>
            )}
            {assets?.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-text-muted">
                  No assets recorded yet — they appear automatically when an investigation references one.
                </td>
              </tr>
            )}
            {assets?.map((asset) => (
              <tr
                key={asset.id}
                onClick={() => openAsset(asset.id)}
                className="cursor-pointer border-b border-hairline last:border-0 hover:bg-surface-raised"
              >
                <td className="px-4 py-3 font-mono text-text-primary">{asset.name}</td>
                <td className="px-4 py-3 text-text-muted">{asset.owner ?? "—"}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs capitalize ${CRITICALITY_STYLES[asset.criticality] ?? ""}`}>
                    {asset.criticality}
                  </span>
                </td>
                <td className={`px-4 py-3 capitalize ${HEALTH_STYLES[asset.health] ?? "text-text-muted"}`}>
                  {asset.health.replace("_", " ")}
                </td>
                <td className="px-4 py-3 text-text-primary">{asset.risk_score}</td>
                <td className="px-4 py-3 text-text-muted">{new Date(asset.last_seen).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {(selected || detailError) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setSelected(null)}>
          <div className="w-full max-w-lg max-h-[85vh] overflow-y-auto rounded-card border border-hairline bg-surface p-5" onClick={(e) => e.stopPropagation()}>
            {detailError && <div className="text-sm text-severity-critical">{detailError}</div>}
            {selected && (
              <>
                <div className="flex items-start justify-between">
                  <div className="font-mono text-sm text-text-primary">{selected.name}</div>
                  <button onClick={() => setSelected(null)} className="text-text-muted hover:text-text-primary">
                    ✕
                  </button>
                </div>
                <div className="mt-1 text-[11px] uppercase tracking-wide text-text-muted">{selected.asset_type.replace("_", " ")}</div>

                <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  <div>
                    <div className="text-text-muted">Criticality</div>
                    <div className={`mt-0.5 capitalize ${CRITICALITY_STYLES[selected.criticality] ? "" : ""}`}>
                      <span className={`rounded-full px-2 py-0.5 ${CRITICALITY_STYLES[selected.criticality] ?? ""}`}>
                        {selected.criticality}
                      </span>
                    </div>
                  </div>
                  <div>
                    <div className="text-text-muted">Health</div>
                    <div className={`mt-0.5 capitalize ${HEALTH_STYLES[selected.health] ?? ""}`}>{selected.health.replace("_", " ")}</div>
                  </div>
                  <div>
                    <div className="text-text-muted">Risk score</div>
                    <div className="mt-0.5 text-text-primary">{selected.risk_score}</div>
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-text-muted">
                  <div>Owner: <span className="text-text-primary">{selected.owner ?? "—"}</span></div>
                  <div>Department: <span className="text-text-primary">{selected.department ?? "—"}</span></div>
                  <div>OS: <span className="text-text-primary">{selected.os ?? "—"}</span></div>
                  <div>Last seen: <span className="text-text-primary">{new Date(selected.last_seen).toLocaleString()}</span></div>
                </div>

                {selected.ai_risk_summary && (
                  <div className="mt-4 rounded border border-cognition/30 bg-cognition/5 p-2.5">
                    <div className="mb-1 text-[10px] uppercase tracking-wide text-cognition">AI risk summary</div>
                    <p className="text-xs text-text-primary">{selected.ai_risk_summary}</p>
                  </div>
                )}

                {selected.open_vulnerabilities.length > 0 && (
                  <div className="mt-4">
                    <div className="mb-1.5 text-xs text-text-muted">Open vulnerabilities</div>
                    <div className="flex flex-wrap gap-1.5">
                      {selected.open_vulnerabilities.map((v, i) => (
                        <span key={i} className="rounded bg-severity-critical/15 px-2 py-0.5 font-mono text-[11px] text-severity-critical">
                          {v.cve ?? "Unknown"} {v.severity ? `(${v.severity})` : ""}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {selected.installed_software.length > 0 && (
                  <div className="mt-4">
                    <div className="mb-1.5 text-xs text-text-muted">Installed software</div>
                    <div className="flex flex-wrap gap-1.5">
                      {selected.installed_software.map((s) => (
                        <span key={s} className="rounded bg-surface-raised px-2 py-0.5 font-mono text-[11px] text-text-primary">
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {selected.running_services.length > 0 && (
                  <div className="mt-4">
                    <div className="mb-1.5 text-xs text-text-muted">Running services</div>
                    <div className="flex flex-wrap gap-1.5">
                      {selected.running_services.map((s) => (
                        <span key={s} className="rounded bg-surface-raised px-2 py-0.5 text-[11px] text-text-primary">
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {selected.security_controls.length > 0 && (
                  <div className="mt-4">
                    <div className="mb-1.5 text-xs text-text-muted">Security controls</div>
                    <div className="flex flex-wrap gap-1.5">
                      {selected.security_controls.map((s) => (
                        <span key={s} className="rounded bg-signal/15 px-2 py-0.5 text-[11px] text-signal">
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mt-4">
                  <div className="mb-1.5 text-xs text-text-muted">
                    Related investigations ({selected.related_investigations.length})
                  </div>
                  {selected.related_investigations.length === 0 ? (
                    <div className="text-xs text-text-muted">No investigations reference this asset yet.</div>
                  ) : (
                    <div className="space-y-1.5">
                      {selected.related_investigations.map((inv) => (
                        <Link
                          key={inv.id}
                          href={`/investigations/${inv.id}`}
                          className="flex items-center justify-between rounded border border-hairline px-2 py-1.5 text-xs hover:bg-surface-raised"
                        >
                          <span className="text-text-primary">{inv.title}</span>
                          <SeverityBadge severity={inv.severity} />
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
