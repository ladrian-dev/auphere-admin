import type { ReactNode } from "react";

import { cn } from "../lib/utils";

type DescriptionItem = { term: ReactNode; detail: ReactNode; mono?: boolean; truncate?: boolean; key?: string };

type DescriptionListProps = {
  items: DescriptionItem[];
  columns?: 1 | 2 | 3;
  dense?: boolean;
  className?: string;
};

/**
 * Term / detail pairs (Bloque C): a client's summary, a channel's card, a
 * receipt. Five different ``<dl>`` became one. ``mono`` is for identifiers
 * that get copied (a reference, a version), never for prose.
 */
function DescriptionList({ items, columns = 1, dense, className }: DescriptionListProps) {
  return (
    <dl
      data-slot="description-list"
      className={cn(
        "grid min-w-0 gap-x-6",
        dense ? "gap-y-1" : "gap-y-2",
        columns === 2 && "sm:grid-cols-2",
        columns === 3 && "sm:grid-cols-3",
        className,
      )}
    >
      {items.map((item, i) => (
        <div key={item.key ?? i} className="flex min-w-0 flex-col gap-1">
          <dt className="text-xs text-muted-foreground">{item.term}</dt>
          <dd className={cn("min-w-0 text-sm", item.mono && "font-mono text-xs", item.truncate && "truncate")} title={item.truncate && typeof item.detail === "string" ? item.detail : undefined}>
            {item.detail}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export { DescriptionList, type DescriptionItem, type DescriptionListProps };
