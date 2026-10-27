import Link from "next/link";

import { cn } from "@nexus/ui";

const TABS = [
  { href: "/router", label: "Perfiles y vista previa" },
  { href: "/router/anomalies", label: "Anomalías" },
] as const;

/** Spec 047 (T150): the two views of the router. */
export function RouterTabs({ current }: { current: (typeof TABS)[number]["href"] }) {
  return (
    <nav aria-label="Router" className="flex gap-1 border-b border-border">
      {TABS.map((t) => (
        <Link
          key={t.href}
          href={t.href}
          aria-current={t.href === current ? "page" : undefined}
          className={cn(
            "-mb-px border-b-2 px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
            t.href === current ? "border-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {t.label}
        </Link>
      ))}
    </nav>
  );
}
