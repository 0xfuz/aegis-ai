import { cn } from "@/lib/utils";

const VERDICT_STYLES: Record<string, string> = {
  malicious: "bg-severity-critical/15 text-severity-critical",
  suspicious: "bg-severity-medium/15 text-severity-medium",
  unknown: "bg-severity-info/15 text-severity-info",
  benign: "bg-severity-low/15 text-severity-low",
};

export function VerdictBadge({ verdict }: { verdict: string }) {
  const style = VERDICT_STYLES[verdict] ?? VERDICT_STYLES.unknown;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs capitalize", style)}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {verdict}
    </span>
  );
}
