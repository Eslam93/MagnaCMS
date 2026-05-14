"use client";

import { FileText, LayoutDashboard, Mic, PenSquare, Settings, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Route } from "next";

import { cn } from "@/lib/utils";

/**
 * Stable sidebar nav for the protected layout. Most routes are
 * stubbed for now — they get real pages in Phase 3+ (P3 content gen,
 * P7 improver, P8 brand voices, P9 usage, P10 settings).
 *
 * `usePathname` highlights the active item so the user always knows
 * where they are. Links use route literals so typedRoutes catches
 * future typos.
 */
const NAV_ITEMS: ReadonlyArray<{
  href: Route;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/generate", label: "Generate", icon: Sparkles },
  { href: "/improve", label: "Improve", icon: PenSquare },
  { href: "/brand-voices", label: "Brand voices", icon: Mic },
  { href: "/usage", label: "Usage", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden w-60 shrink-0 border-r bg-card md:flex md:flex-col">
      <div className="border-b px-6 py-4">
        <Link href="/dashboard" className="text-lg font-bold">
          MagnaCMS
        </Link>
      </div>
      <nav className="flex-1 space-y-1 p-4">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
