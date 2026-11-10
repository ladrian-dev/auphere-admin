"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";

import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator, cn } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { useCrumbNames } from "./crumb-names";
import { crumbsFor, type CrumbLabel } from "./crumbs-v2";

/**
 * Spec 047 (R47.1): las migas del marco nuevo, con el `breadcrumb` de
 * `@nexus/ui`. El último elemento es la página y no es un enlace. En pantallas
 * estrechas se quedan las dos últimas: lo de antes está en el menú.
 */
export function ShellBreadcrumbs({ className }: { className?: string }) {
  const t = useT();
  const pathname = usePathname();
  const names = useCrumbNames();
  const crumbs = crumbsFor(pathname, names);
  if (crumbs.length === 0) return null;
  const text = (label: CrumbLabel) => ("text" in label ? label.text : t(label.key, label.vars));
  const keepFrom = crumbs.length - 2;

  return (
    <Breadcrumb aria-label={t("shell.crumbs.label")} className={cn("min-w-0", className)}>
      <BreadcrumbList className="flex-nowrap gap-1 text-sm">
        {crumbs.map((crumb, i) => {
          const hideNarrow = i < keepFrom ? "max-sm:hidden" : undefined;
          return (
            <Fragment key={`${i}-${crumb.href ?? "here"}`}>
              {i > 0 ? <BreadcrumbSeparator className={cn(i <= keepFrom ? "max-sm:hidden" : undefined)} /> : null}
              <BreadcrumbItem className={cn("min-w-0", hideNarrow)}>
                {crumb.href ? (
                  <BreadcrumbLink
                    render={<Link href={crumb.href} />}
                    className="block max-w-64 truncate rounded-sm py-1"
                  >
                    {text(crumb.label)}
                  </BreadcrumbLink>
                ) : (
                  <BreadcrumbPage className="block max-w-64 truncate font-medium">{text(crumb.label)}</BreadcrumbPage>
                )}
              </BreadcrumbItem>
            </Fragment>
          );
        })}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
