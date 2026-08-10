"use client";
import { useParams } from "next/navigation";
import { PlaceholderWorkspace } from "@/components/investigations/factual-workspace";
export default function ReportsPage() { const { id } = useParams<{ id: string }>(); return <PlaceholderWorkspace id={id} title="Reports" />; }
