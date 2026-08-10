import { cn } from "@/lib/utils";

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-severity-critical/15 text-severity-critical",
  high: "bg-severity-high/15 text-severity-high",
  medium: "bg-severity-medium/15 text-severity-medium",
  low: "bg-severity-low/15 text-severity-low",
  info: "bg-severity-info/15 text-severity-info",
};

export function SeverityBadge({ severity }: { severity: string }) {
  const style = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.info;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs capitalize", style)}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {severity}
    </span>
  );
}
