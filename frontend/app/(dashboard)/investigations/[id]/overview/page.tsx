"use client";

import { useParams } from "next/navigation";
import { OverviewWorkspace } from "@/components/investigations/factual-workspace";

export default function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  return <OverviewWorkspace id={id} />;
}
