"use client";

import { MoreHorizontal } from "lucide-react";
import Link from "next/link";

import { Button, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@nexus/ui";

/** One action of a row: a link (``href``) or something done here (``onSelect``). */
export type RowAction = {
  label: string;
  href?: string;
  onSelect?: () => void;
  primary?: boolean;
  disabled?: boolean;
};

function key(a: RowAction): string {
  return `${a.href ?? ""}${a.label}`;
}

/**
 * The actions of one row (owner's rule, see ``row-actions-rule.ts``): the
 * primary as a button while the list is small, or all of them behind «⋯»,
 * the primary first and in bold.
 */
export function RowActions({ actions, menu, ariaLabel }: { actions: RowAction[]; menu: boolean; ariaLabel: string }) {
  const primary = actions.find((a) => a.primary) ?? actions[0];
  if (!primary) return null;
  if (!menu) {
    return primary.href ? (
      <Button size="sm" nativeButton={false} render={<Link href={primary.href} />}>
        {primary.label}
      </Button>
    ) : (
      <Button size="sm" onClick={primary.onSelect} disabled={primary.disabled}>
        {primary.label}
      </Button>
    );
  }
  const rest = actions.filter((a) => a !== primary);
  const item = (a: RowAction, bold = false) =>
    a.href ? (
      <DropdownMenuItem key={key(a)} render={<Link href={a.href} />} className={bold ? "font-medium" : undefined}>
        {a.label}
      </DropdownMenuItem>
    ) : (
      <DropdownMenuItem key={key(a)} onClick={a.onSelect} disabled={a.disabled} className={bold ? "font-medium" : undefined}>
        {a.label}
      </DropdownMenuItem>
    );
  return (
    <DropdownMenu>
      <DropdownMenuTrigger aria-label={ariaLabel} className="inline-flex size-8 shrink-0 items-center justify-center rounded-sm hover:bg-muted" data-slot="row-actions">
        <MoreHorizontal aria-hidden="true" className="size-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {item(primary, true)}
        {rest.length > 0 ? <DropdownMenuSeparator /> : null}
        {rest.map((a) => item(a))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
