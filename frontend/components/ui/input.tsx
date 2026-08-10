import { InputHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "w-full rounded border border-hairline bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
