"use client";
import { useParams } from "next/navigation";
import { NotesWorkspace } from "@/components/investigations/notes-workspace";
export default function NotesPage() { const { id } = useParams<{ id: string }>(); return <NotesWorkspace id={id} />; }
