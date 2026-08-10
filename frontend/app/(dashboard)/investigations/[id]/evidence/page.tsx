"use client";

import { useParams } from "next/navigation";
import { EvidenceWorkspace } from "@/components/investigations/factual-workspace";

export default function EvidencePage() {
  const { id } = useParams<{ id: string }>();
  return <EvidenceWorkspace id={id} />;
}
