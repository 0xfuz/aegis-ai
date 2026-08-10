import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-card border border-hairline bg-surface p-4", className)}
      {...props}
    />
  );
}

export function CardLabel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("text-xs text-text-muted", className)} {...props} />;
}

export function CardValue({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("font-display text-2xl font-medium text-text-primary", className)} {...props} />
  );
}
