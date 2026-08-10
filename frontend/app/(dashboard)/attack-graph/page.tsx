"use client";

import { useRouter } from "next/navigation";
import { Network } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function AttackGraphIndexPage() {
  const router = useRouter();

  return (
    <div>
      <h1 className="font-display text-xl font-medium text-text-primary">Attack graph</h1>
      <div className="mt-6 flex flex-col items-center justify-center rounded-card border border-hairline bg-surface px-6 py-16 text-center">
        <Network size={28} className="mb-3 text-text-muted" aria-hidden />
        <p className="max-w-sm text-sm text-text-primary">
          Attack graphs are generated from active investigations.
        </p>
        <Button className="mt-4" onClick={() => router.push("/investigations")}>
          View Investigations
        </Button>
      </div>
    </div>
  );
}
