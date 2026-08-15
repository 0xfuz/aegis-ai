"use client";
import { useParams } from "next/navigation";
import { ReportsWorkspace } from "@/components/investigations/reports-workspace";
export default function ReportsPage() { const { id } = useParams<{ id: string }>(); return <ReportsWorkspace id={id} />; }
