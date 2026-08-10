"use client";

import { useEffect, useState } from "react";
import { Search, Bell, ChevronDown, LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

export function Topbar() {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [paletteHint, setPaletteHint] = useState("Ctrl K");

  useEffect(() => {
    // Avoid a server/client render mismatch — the platform-specific
    // shortcut label is only known once we're in the browser.
    const isMac = /Mac|iPod|iPhone|iPad/.test(navigator.platform);
    setPaletteHint(isMac ? "⌘K" : "Ctrl K");
  }, []);

  return (
    <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-hairline bg-surface px-4">
      <button
        type="button"
        className="flex w-80 items-center gap-2 rounded border border-hairline bg-surface-raised px-3 py-1.5 text-sm text-text-muted hover:border-hairline/70"
        aria-label="Open command palette"
      >
        <Search size={14} aria-hidden />
        <span className="flex-1 text-left">Ask Aegis or search…</span>
        <kbd className="rounded border border-hairline px-1.5 py-0.5 font-mono text-[10px]">
          {paletteHint}
        </kbd>
      </button>

      <div className="flex items-center gap-3">
        <button
          type="button"
          className="rounded p-2 text-text-muted hover:bg-surface-raised hover:text-text-primary"
          aria-label="Notifications"
        >
          <Bell size={16} aria-hidden />
        </button>

        <div className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            className="flex items-center gap-2 rounded px-2 py-1.5 text-sm text-text-primary hover:bg-surface-raised"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-signal/20 text-xs font-medium text-signal">
              {user?.full_name?.slice(0, 2).toUpperCase() ?? "?"}
            </span>
            <ChevronDown size={14} aria-hidden />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-full mt-1 w-44 rounded border border-hairline bg-surface-raised py-1 shadow-lg">
              <button
                type="button"
                onClick={() => logout()}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-text-primary hover:bg-void"
              >
                <LogOut size={14} aria-hidden />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
