import { Button } from "@/components/ui/button";
import type { ReactNode } from "react";

type StatePanelProps = {
  title: string;
  children: ReactNode;
};

function StatePanel({ title, children }: StatePanelProps) {
  return (
    <section className="rounded-card border border-hairline bg-surface p-4 text-sm text-text-muted" aria-labelledby={`state-${title}`}>
      <h2 id={`state-${title}`} className="font-display text-base text-text-primary">{title}</h2>
      <div className="mt-1">{children}</div>
    </section>
  );
}

export function LoadingState({ title = "Loading", message = "Loading the requested information." }: { title?: string; message?: string }) {
  return <div role="status" aria-live="polite" aria-busy="true"><StatePanel title={title}>{message}</StatePanel></div>;
}

export function EmptyState({ title = "No data available", message = "There is nothing to show yet." }: { title?: string; message?: string }) {
  return <StatePanel title={title}>{message}</StatePanel>;
}

export function PermissionDeniedState() {
  return <div role="alert"><StatePanel title="Permission denied">You do not have permission to view this information.</StatePanel></div>;
}

export function NotFoundState() {
  return <div role="alert"><StatePanel title="Not found">The requested resource is unavailable.</StatePanel></div>;
}

export function RetryableErrorState({ onRetry, title = "Unable to load", message = "Please try again." }: { onRetry: () => void; title?: string; message?: string }) {
  return (
    <div role="alert" aria-live="assertive">
      <StatePanel title={title}>
        <p>{message}</p>
        <Button type="button" variant="secondary" className="mt-3" onClick={onRetry}>Retry</Button>
      </StatePanel>
    </div>
  );
}

export function DegradedState({ message = "Some information is temporarily unavailable. Displayed data may be incomplete." }: { message?: string }) {
  return <div role="status" aria-live="polite"><StatePanel title="Limited availability">{message}</StatePanel></div>;
}
