"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const TABS = [
  { slug: "", label: "Keys" },
  { slug: "tenants", label: "Tenants" },
  { slug: "limits", label: "Límites" },
  { slug: "usage", label: "Uso" },
  { slug: "wallet", label: "Consumo" },
  { slug: "models", label: "Modelos" },
  { slug: "knowledge", label: "Conocimiento" },
  { slug: "receipts", label: "Recibos" },
  { slug: "audit", label: "Auditoría" },
] as const;

/**
 * Editorial tab bar — same underline-only pattern as the tenant tabs
 * (``tenants/[id]/tabs.tsx``): 1px primary underline + weight bump for
 * the active tab, no pills, no chrome.
 */
export function PartnerTabs({ partnerId }: { partnerId: string }) {
  const pathname = usePathname();
  const base = `/partners/${partnerId}`;

  return (
    <nav
      role="tablist"
      aria-label="Secciones del partner"
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
            key={tab.slug || "keys"}
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
                active ? "bg-[color:var(--color-primary)]" : "bg-transparent",
              )}
            />
          </Link>
        );
      })}
    </nav>
  );
}
