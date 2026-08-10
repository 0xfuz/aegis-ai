import { Construction } from "lucide-react";

export function ComingSoon({ title, phase }: { title: string; phase: string }) {
  return (
    <div>
      <h1 className="font-display text-xl font-medium text-text-primary">{title}</h1>
      <div className="mt-6 flex flex-col items-center justify-center rounded-card border border-hairline bg-surface px-6 py-16 text-center">
        <Construction size={28} className="mb-3 text-text-muted" aria-hidden />
        <p className="text-sm text-text-primary">{title} isn&apos;t built yet</p>
        <p className="mt-1 text-sm text-text-muted">{phase}</p>
      </div>
    </div>
  );
}
