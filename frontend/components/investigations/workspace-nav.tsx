"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const items = [
  ["Overview", "overview"], ["Evidence", "evidence"], ["Timeline", "timeline"],
  ["Indicators", "indicators"], ["Entities", "entities"], ["Attack Graph", "relationships"],
  ["Intelligence", "intelligence"],
  ["Findings", "findings"], ["MITRE ATT&CK", "mitre"], ["Notes", "notes"], ["Reports", "reports"],
  ["Audit Trail", "audit"],
] as const;

export function WorkspaceNav({ investigationId }: { investigationId: string }) {
  const pathname = usePathname();
  return <nav aria-label="Investigation workspace" className="mb-5 flex flex-wrap gap-1 border-b border-hairline pb-3">
    {items.map(([label, segment]) => {
      const href = `/investigations/${investigationId}/${segment}`;
      return <Link key={segment} href={href} className={cn("rounded px-2.5 py-1.5 text-xs", pathname === href ? "bg-signal/15 text-signal" : "text-text-muted hover:bg-surface-raised hover:text-text-primary")}>{label}</Link>;
    })}
    <Link href={`/investigations/${investigationId}`} className="ml-auto rounded px-2.5 py-1.5 text-xs text-text-muted hover:bg-surface-raised">Legacy view</Link>
  </nav>;
}
