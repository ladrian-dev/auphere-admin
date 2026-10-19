"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { NavTabs } from "@nexus/ui";

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

/**
 * Spec 037: a record's tabs grouped by the question they answer, with the
 * group's name above — **the same `NavTabs` as the client page of the partner
 * console** (spec 017 R2), so both consoles read the same way (Jakob).
 */
export function ProfileTabs({ base, groups, label }: { base: string; groups: ProfileTabGroup[]; label: string }) {
  const pathname = usePathname();
  const current = currentTab(
    pathname,
    base,
    groups.flatMap((g) => g.tabs.map((t) => t.seg)),
  );
  return (
    <NavTabs
      ariaLabel={label}
      current={current || "__summary__"}
      marks={{ incident: "Necesita atención", draft: "Sin publicar" }}
      groups={groups.map((g) => ({
        key: g.key,
        label: g.label,
        items: g.tabs.map((t) => ({
          key: t.seg || "__summary__",
          label: t.label,
          href: t.seg ? `${base}/${t.seg}` : base,
          ...(t.mark ? { mark: t.mark } : {}),
        })),
      }))}
      renderLink={({ href, className, children, ...rest }) => (
        <Link href={href} className={className} {...rest}>
          {children}
        </Link>
      )}
    />
  );
}
