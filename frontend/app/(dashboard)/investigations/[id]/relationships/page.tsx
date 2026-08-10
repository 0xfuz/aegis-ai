"use client";

import { useParams } from "next/navigation";
import { CanonicalGraphWorkspace } from "@/components/investigations/canonical-graph-workspace";

export default function RelationshipsPage() {
  const { id } = useParams<{ id: string }>();
  return <CanonicalGraphWorkspace id={id} />;
}
