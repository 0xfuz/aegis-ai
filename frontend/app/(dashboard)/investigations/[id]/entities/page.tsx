"use client";

import { useParams } from "next/navigation";
import { EntitiesWorkspace } from "@/components/investigations/factual-workspace";

export default function EntitiesPage() {
  const { id } = useParams<{ id: string }>();
  return <EntitiesWorkspace id={id} />;
}
