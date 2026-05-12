"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const TABS = [
  { slug: "", label: "Resumen" },
  { slug: "agent", label: "Agente" },
  { slug: "conversations", label: "Conversaciones" },
  { slug: "connectors", label: "Connectors" },
  { slug: "isolation", label: "Aislamiento" },
] as const;

/**
 * Editorial tab bar — underline-only, no chrome. Active state uses a
 * 1px primary underline plus weight bump; everything else stays mute.
 * No pill backgrounds, no shadow, no rounded boxes — that would
 * compete with the page header for visual weight.
 */
export function TenantTabs({ tenantId }: { tenantId: string }) {
  const pathname = usePathname();
  const base = `/tenants/${tenantId}`;

  return (
    <nav
      role="tablist"
      aria-label="Secciones del tenant"
      className="-mb-px flex items-center gap-1 overflow-x-auto"
    >
      {TABS.map((tab) => {
        const href = tab.slug ? `${base}/${tab.slug}` : base;
        const active =
          tab.slug === ""
            ? pathname === base
            : pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={tab.slug || "overview"}
            href={href}
            role="tab"
            aria-selected={active}
            className={cn(
              "relative px-3 py-2 text-sm transition-colors outline-none",
              "focus-visible:ring-2 focus-visible:ring-ring rounded-sm",
              active
                ? "text-foreground font-medium"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
            <span
              aria-hidden="true"
              className={cn(
                "absolute inset-x-2 -bottom-px h-px transition-colors",
                active
                  ? "bg-[color:var(--color-primary)]"
                  : "bg-transparent",
              )}
            />
          </Link>
        );
      })}
    </nav>
  );
}
