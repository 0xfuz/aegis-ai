"use client";

import { useParams } from "next/navigation";
import { FindingsWorkspace } from "@/components/investigations/findings-workspace";

export default function FindingsPage() {
  const { id } = useParams<{ id: string }>();
  return <FindingsWorkspace id={id} />;
}
