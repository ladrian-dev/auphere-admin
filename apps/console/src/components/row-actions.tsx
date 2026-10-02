"use client";

import { MoreHorizontal } from "lucide-react";
import Link from "next/link";

import { Button, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@nexus/ui";

export type RowAction = { label: string; href: string; primary?: boolean };

/** The actions of one row: the primary as a button, or all of them behind «⋯». */
export function RowActions({ actions, menu, ariaLabel }: { actions: RowAction[]; menu: boolean; ariaLabel: string }) {
  const primary = actions.find((a) => a.primary) ?? actions[0];
  if (!primary) return null;
  if (!menu) {
    return (
      <Button size="sm" nativeButton={false} render={<Link href={primary.href} />}>
        {primary.label}
      </Button>
    );
  }
  const rest = actions.filter((a) => a !== primary);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger aria-label={ariaLabel} className="inline-flex size-8 shrink-0 items-center justify-center rounded-sm hover:bg-muted" data-slot="row-actions">
        <MoreHorizontal aria-hidden="true" className="size-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuItem render={<Link href={primary.href} />} className="font-medium">
          {primary.label}
        </DropdownMenuItem>
        {rest.length > 0 ? <DropdownMenuSeparator /> : null}
        {rest.map((a) => (
          <DropdownMenuItem key={a.href + a.label} render={<Link href={a.href} />}>
            {a.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
