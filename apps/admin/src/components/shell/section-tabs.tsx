import Link from "next/link";

import { cn } from "@nexus/ui";

export type SectionTab = { href: string; label: string };

/**
 * The views of one section of the sidebar, as links under the page header
 * (Router, Canales, Constructor). The current one carries `aria-current`.
 */
export function SectionTabs({ label, tabs, current }: { label: string; tabs: readonly SectionTab[]; current: string }) {
  return (
    <nav aria-label={label} className="flex gap-1 overflow-x-auto border-b border-border">
      {tabs.map((t) => (
        <Link
          key={t.href}
          href={t.href}
          aria-current={t.href === current ? "page" : undefined}
          className={cn(
            "-mb-px shrink-0 border-b-2 px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
            t.href === current ? "border-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {t.label}
        </Link>
      ))}
    </nav>
  );
}
