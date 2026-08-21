"use client";

import { useParams } from "next/navigation";
import { MitreWorkspace } from "@/components/investigations/mitre-workspace";

export default function MitrePage() {
  const { id } = useParams<{ id: string }>();
  return <MitreWorkspace id={id} />;
}
