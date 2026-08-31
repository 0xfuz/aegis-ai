"use client";
import { useParams } from "next/navigation";
import { AuditTrailWorkspace } from "@/components/investigations/audit-trail-workspace";
export default function AuditPage() { const { id } = useParams<{ id: string }>(); return <AuditTrailWorkspace id={id} />; }
