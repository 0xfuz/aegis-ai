"use client";

import { useParams } from "next/navigation";
import { IndicatorsWorkspace } from "@/components/investigations/factual-workspace";

export default function IndicatorsPage() {
  const { id } = useParams<{ id: string }>();
  return <IndicatorsWorkspace id={id} />;
}
