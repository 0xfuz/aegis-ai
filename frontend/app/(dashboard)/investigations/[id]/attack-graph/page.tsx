"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { LoadingState } from "@/components/ui/async-state";

/** Compatibility route: the canonical Investigation Attack Graph is /relationships. */
export default function InvestigationAttackGraphPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  useEffect(() => { if (id) router.replace(`/investigations/${encodeURIComponent(id)}/relationships`); }, [id, router]);
  return <LoadingState title="Opening Attack Graph" message="Opening the authoritative Investigation relationships workspace." />;
}
