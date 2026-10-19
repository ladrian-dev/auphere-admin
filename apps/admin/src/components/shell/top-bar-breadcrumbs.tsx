"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
  cn,
} from "@nexus/ui";

import { useCrumbNames } from "./crumb-names";
import { crumbsFor } from "./crumbs";

/** The trail in the top bar: where this page sits, each step a link back. */
export function TopBarBreadcrumbs() {
  const crumbs = crumbsFor(usePathname(), useCrumbNames());
  return (
    <Breadcrumb className="min-w-0">
      <BreadcrumbList className="flex-nowrap">
        {crumbs.map((c, i) => {
          // On a phone, only the last two steps: the rest is one tap back.
          const far = i < crumbs.length - 2;
          return (
            <Fragment key={`${i}-${c.label}`}>
              {i > 0 ? <BreadcrumbSeparator className={cn(far && "max-md:hidden")} /> : null}
              <BreadcrumbItem className={cn("min-w-0", far && "max-md:hidden")}>
                {c.href ? (
                  <BreadcrumbLink render={<Link href={c.href} />} className="truncate">
                    {c.label}
                  </BreadcrumbLink>
                ) : (
                  <BreadcrumbPage className="truncate">{c.label}</BreadcrumbPage>
                )}
              </BreadcrumbItem>
            </Fragment>
          );
        })}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
