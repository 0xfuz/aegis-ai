"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  Settings,
  ShieldAlert,
  Users,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const GLOBAL_SECTIONS = [
  { label: "Operations", items: [
    { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard, permission: "investigation:read" },
    { label: "Cases", href: "/investigations", icon: ShieldAlert, permission: "investigation:read" },
    { label: "Alert Triage", href: "/alert-triage", icon: ShieldAlert, permission: "investigation:read" },
  ] },
  { label: "Security / Platform", items: [
    { label: "Assets", href: "/assets", icon: ShieldAlert, permission: "assets:read" },
    { label: "Threat Intelligence", href: "/threat-intel", icon: ShieldAlert, permission: "threat_intel:read" },
  ] },
] as const;

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="px-3 py-1 text-[10px] font-medium uppercase tracking-wider text-text-muted">{children}</div>;
}

export function Sidebar() {
  const pathname = usePathname();
  const { user, hasPermission } = useAuth();
  const isAdmin = user?.role.name === "admin";
  const [openCount, setOpenCount] = useState<number | null>(null);

  useEffect(() => {
    if (!user) return;
    Promise.resolve(apiFetch<{ open_investigations: number }>("/api/v1/investigations/dashboard-summary"))
      .then((data) => setOpenCount(data.open_investigations))
      .catch(() => setOpenCount(null));
  }, [user]);

  const linkClass = (active: boolean) => cn(
    "flex items-center gap-3 rounded px-3 py-2 text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal",
    active ? "border-l-2 border-signal bg-surface-raised text-signal" : "text-text-muted hover:bg-surface-raised hover:text-text-primary",
  );

  return (
    <aside className="flex h-screen w-60 flex-shrink-0 flex-col border-r border-hairline bg-surface">
      <div className="px-4 py-5 font-display text-lg font-medium">Aegis AI</div>
      <nav className="flex-1 space-y-3 px-2" aria-label="Primary navigation">
        {GLOBAL_SECTIONS.map((section) => {
          const items = section.items.filter((item) => hasPermission(item.permission));
          if (items.length === 0) return null;
          return <div key={section.label}><SectionLabel>{section.label}</SectionLabel>{items.map((item) => { const Icon = item.icon; const active = item.href === "/investigations" ? pathname === "/investigations" : pathname?.startsWith(item.href); return <Link key={item.href} href={item.href} className={linkClass(Boolean(active))}><Icon size={16} aria-hidden /><span className="flex-1">{item.label}</span>{item.label === "Cases" && openCount !== null && openCount > 0 && <span className="rounded-full bg-severity-critical px-1.5 text-[10px] text-white">{openCount}</span>}</Link>; })}</div>;
        })}

        {isAdmin && <><div className="my-2 border-t border-hairline" /><Link href="/settings" className={linkClass(Boolean(pathname?.startsWith("/settings")))}><Settings size={16} aria-hidden />Settings</Link><Link href="/user-management" className={linkClass(Boolean(pathname?.startsWith("/user-management")))}><Users size={16} aria-hidden />User management</Link></>}
      </nav>
      {user && <div className="border-t border-hairline px-4 py-3"><div className="truncate text-sm text-text-primary">{user.full_name}</div><div className="truncate text-xs text-text-muted">{user.role.name.replace("_", " ")}</div></div>}
    </aside>
  );
}
