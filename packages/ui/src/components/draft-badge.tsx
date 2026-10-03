import type { ReactNode } from "react";

import { cn } from "../lib/utils";
import { StatusBadge } from "./status-badge";

type DraftBadgeProps = {
  /** The draft version, if any. */
  draft: number | null | undefined;
  /** The active version, if any. */
  active: number | null | undefined;
  /** «Borrador v{v}» / «Activa v{v}» / «Sin publicar» — the caller's words. */
  draftLabel: (v: number) => ReactNode;
  activeLabel: (v: number) => ReactNode;
  noneLabel?: ReactNode;
  className?: string;
};

/**
 * Draft vs active, said once and the same way everywhere (Bloque C). A
 * draft is ``info`` (pending), an active version is ``positive``; a client
 * with neither says so instead of showing nothing.
 */
function DraftBadge({ draft, active, draftLabel, activeLabel, noneLabel, className }: DraftBadgeProps) {
  if (draft == null && active == null) {
    return noneLabel ? (
      <StatusBadge tone="muted" className={className}>
        {noneLabel}
      </StatusBadge>
    ) : null;
  }
  return (
    <span data-slot="draft-badge" className={cn("inline-flex flex-wrap items-center gap-2", className)}>
      {draft != null ? <StatusBadge tone="info">{draftLabel(draft)}</StatusBadge> : null}
      {active != null ? <StatusBadge tone="positive">{activeLabel(active)}</StatusBadge> : null}
    </span>
  );
}

export { DraftBadge, type DraftBadgeProps };
