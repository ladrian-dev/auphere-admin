"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { NavTabs, useIsMobile } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { Role } from "@/lib/permissions";

import { navGroupsFor } from "./client-nav-model";

/**
 * Las pestañas de la ficha (spec 017, R2). Sustituye a la fila plana de
 * diez: los mismos diez destinos, agrupados en tres preguntas y filtrados
 * por rol. La decisión vive en `client-nav-model`; esto solo la pinta.
 */
export function ClientNav({
  refId,
  role,
  draftScreens,
  incidents,
}: {
  refId: string;
  role: Role;
  draftScreens?: readonly string[];
  incidents?: readonly string[];
}) {
  const t = useT();
  const pathname = usePathname();
  const compact = useIsMobile();
  const base = `/clients/${encodeURIComponent(refId)}`;
  const model = navGroupsFor(role, base, { draftScreens, incidents });

  // La pestaña actual es la de ruta más larga que sea prefijo de la actual:
  // así `/agent/versions` sigue marcando «Agente» y no «Resumen».
  const current =
    model
      .flatMap((g) => g.items)
      .map((i) => ({ key: i.key, path: i.href.split("#")[0] ?? i.href }))
      .filter((i) => i.path === pathname || pathname.startsWith(`${i.path}/`))
      .sort((a, b) => b.path.length - a.path.length)[0]?.key ?? "overview";

  const groups = model.map((g) => ({
    key: g.key,
    label: t(g.label),
    items: g.items.map((i) => ({ key: i.key, label: t(i.label), href: i.href, ...(i.mark ? { mark: i.mark } : {}) })),
  }));

  return (
    <NavTabs
      ariaLabel={t("clients.nav.label")}
      groups={groups}
      current={current}
      compact={compact}
      className="-mt-2"
      marks={{ draft: t("clients.nav.mark.draft"), incident: t("clients.nav.mark.incident") }}
      markSuffix={{ draft: t("clients.nav.suffix.draft"), incident: t("clients.nav.suffix.incident") }}
      renderLink={({ href, className, children, ...rest }) => (
        <Link href={href} className={className} {...rest}>
          {children}
        </Link>
      )}
    />
  );
}
