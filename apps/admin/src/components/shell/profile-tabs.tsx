"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";

import { StatusDot, cn } from "@nexus/ui";

export type ProfileTab = { seg: string; label: string; mark?: "incident" | "draft" };
export type ProfileTabGroup = { key: string; label: string; tabs: ProfileTab[] };

/** The tab whose path is the longest prefix of the address: `/agent?x` → Agente. */
export function currentTab(pathname: string, base: string, segs: readonly string[]): string {
  const match = segs
    .filter((seg) => seg !== "")
    .filter((seg) => pathname === `${base}/${seg}` || pathname.startsWith(`${base}/${seg}/`))
    .sort((a, b) => b.length - a.length)[0];
  return match ?? "";
}

const MARK_LABEL = { incident: "Necesita atención", draft: "Sin publicar" } as const;

/**
 * Spec 036: a record's tabs in **one row**, groups told apart by a hairline
 * (Gestalt proximity) instead of a heading above each — the content starts a
 * row higher. Each group is a `role="group"` with its name, so a screen reader
 * still hears «Conectar: Canales, Conectores…». On a narrow screen the row
 * scrolls sideways.
 */
export function ProfileTabs({ base, groups, label }: { base: string; groups: ProfileTabGroup[]; label: string }) {
  const pathname = usePathname();
  const current = currentTab(
    pathname,
    base,
    groups.flatMap((g) => g.tabs.map((t) => t.seg)),
  );
  return (
    <nav aria-label={label} className="-mx-1 overflow-x-auto border-b border-border">
      <div className="flex w-max items-center gap-1 px-1">
        {groups.map((g, gi) => (
          <Fragment key={g.key}>
            {gi > 0 ? <span aria-hidden="true" className="mx-2 h-4 w-px bg-border" /> : null}
            <div role="group" aria-label={g.label} className="flex items-center gap-1">
              {g.tabs.map((t) => {
                const active = t.seg === current;
                return (
                  <Link
                    key={t.seg || "summary"}
                    href={t.seg ? `${base}/${t.seg}` : base}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "-mb-px inline-flex items-center gap-2 border-b-2 px-3 py-2 text-sm whitespace-nowrap outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      active
                        ? "border-foreground font-medium text-foreground"
                        : "border-transparent text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {t.label}
                    {t.mark ? (
                      <StatusDot tone={t.mark === "incident" ? "danger" : "info"} label={MARK_LABEL[t.mark]} />
                    ) : null}
                  </Link>
                );
              })}
            </div>
          </Fragment>
        ))}
      </div>
    </nav>
  );
}
