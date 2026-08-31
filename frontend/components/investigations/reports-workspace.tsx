"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ApiError, downloadInvestigationReport } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DegradedState, PermissionDeniedState, NotFoundState, RetryableErrorState } from "@/components/ui/async-state";
import { WorkspaceNav } from "./workspace-nav";

type ReportType = "executive" | "technical";
type ReportFormat = "markdown" | "pdf";
type DownloadState = "idle" | "generating" | "downloading" | "success" | "denied" | "not-found" | "unavailable" | "error";

const reports: Array<{ type: ReportType; title: string; description: string; permission: string }> = [
  { type: "technical", title: "Technical report", description: "Evidence, timeline, indicators, and analyst notes from authoritative Investigation records.", permission: "reports:generate_technical" },
  { type: "executive", title: "Executive report", description: "A bounded leadership-oriented summary from authoritative Investigation records.", permission: "reports:generate_executive" },
];

function reportPath(id: string, type: ReportType, format: ReportFormat) {
  return `/api/v1/investigations/${encodeURIComponent(id)}/report?type=${type}&format=${format}`;
}

export function ReportsWorkspace({ id }: { id: string }) {
  const { hasPermission, isLoading } = useAuth();
  const [state, setState] = useState<DownloadState>("idle");
  const [active, setActive] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const available = reports.filter(report => hasPermission(report.permission));

  useEffect(() => () => controller.current?.abort(), []);
  const download = useCallback(async (type: ReportType, format: ReportFormat) => {
    if (active || !id) return;
    const key = `${type}-${format}`;
    const nextController = new AbortController();
    controller.current = nextController;
    setActive(key); setState("generating");
    try {
      await downloadInvestigationReport(reportPath(id, type, format), { signal: nextController.signal, onDownloading: () => setState("downloading") });
      if (!nextController.signal.aborted) setState("success");
    } catch (error) {
      if (nextController.signal.aborted) return;
      if (error instanceof ApiError) setState(error.status === 403 ? "denied" : error.status === 404 ? "not-found" : error.status === 503 ? "unavailable" : "error");
      else setState("error");
    } finally {
      if (!nextController.signal.aborted) setActive(null);
      if (controller.current === nextController) controller.current = null;
    }
  }, [active, id]);

  return <>
    <div className="mb-2 text-xs text-text-muted"><Link href="/investigations">Cases</Link> / Investigation workspace</div>
    <h1 className="font-display text-lg text-text-primary">Reports</h1>
    <WorkspaceNav investigationId={id} />
    <section aria-labelledby="reports-description" className="mb-4"><h2 id="reports-description" className="font-display text-base">Investigation reports</h2><p className="mt-1 text-sm text-text-muted">Reports are generated on demand from authoritative Investigation records. They do not create Findings, MITRE mappings, claims, or actions.</p></section>
    {state === "denied" && <PermissionDeniedState />}
    {state === "not-found" && <NotFoundState />}
    {state === "unavailable" && <div className="space-y-3"><DegradedState message="Report generation is temporarily unavailable." /><Button type="button" variant="secondary" onClick={() => setState("idle")}>Try another report</Button></div>}
    {state === "error" && <RetryableErrorState title="Unable to generate report" message="The report could not be generated. Please try again." onRetry={() => setState("idle")} />}
    {state !== "denied" && state !== "not-found" && state !== "unavailable" && state !== "error" && <>
      <p role="status" aria-live="polite" className="mb-3 text-sm text-text-muted">{state === "generating" ? "Generating report…" : state === "downloading" ? "Downloading report…" : state === "success" ? "Report download started." : "Choose an authorized report format."}</p>
      {!isLoading && available.length === 0 ? <PermissionDeniedState /> : <div className="grid gap-4 md:grid-cols-2">{reports.map(report => <Card key={report.type}><h3 className="font-display text-base">{report.title}</h3><p className="mt-2 text-sm text-text-muted">{report.description}</p>{hasPermission(report.permission) ? <div className="mt-4 flex flex-wrap gap-2"><Button type="button" disabled={Boolean(active)} onClick={() => void download(report.type, "markdown")}>{active === `${report.type}-markdown` ? "Generating…" : "Download Markdown"}</Button><Button type="button" variant="secondary" disabled={Boolean(active)} onClick={() => void download(report.type, "pdf")}>{active === `${report.type}-pdf` ? "Generating…" : "Download PDF"}</Button></div> : <p className="mt-4 text-sm text-text-muted">You do not have permission to generate this report.</p>}</Card>)}</div>}
    </>}
  </>;
}
