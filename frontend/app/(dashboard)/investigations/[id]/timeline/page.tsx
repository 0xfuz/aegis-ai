"use client";

import { useParams } from "next/navigation";
import { TimelineWorkspace } from "@/components/investigations/factual-workspace";

export default function TimelinePage() {
  const { id } = useParams<{ id: string }>();
  return <TimelineWorkspace id={id} />;
}
