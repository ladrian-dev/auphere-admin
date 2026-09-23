import type { ReactNode } from "react";

import { cn } from "../lib/utils";

type DescriptionItem = {
  term: ReactNode;
  detail: ReactNode;
  /** Identifiers that get copied (a reference, a version), never prose. */
  mono?: boolean;
  truncate?: boolean;
  /** Right-align the detail (numbers in a narrow inspector). */
  align?: "start" | "end";
  key?: string;
};

type DescriptionListProps = {
  items: DescriptionItem[];
  /** ``stacked``: term above detail, in ``columns``. ``inline``: term left,
   *  detail right, one pair per row (a card's facts, an inspector). */
  layout?: "stacked" | "inline";
  columns?: 1 | 2 | 3;
  dense?: boolean;
  className?: string;
};

/**
 * Term / detail pairs (Bloque C): a client's summary, a channel's card, a
 * receipt. Five different ``<dl>`` became one. ``mono`` is for identifiers
 * that get copied (a reference, a version), never for prose.
 */
function DescriptionList({ items, layout = "stacked", columns = 1, dense, className }: DescriptionListProps) {
  if (layout === "inline") {
    return (
      <dl data-slot="description-list" data-layout="inline" className={cn("grid min-w-0 grid-cols-[auto_1fr] gap-x-4 text-sm", dense ? "gap-y-1" : "gap-y-2", className)}>
        {items.map((item, i) => (
          <div key={item.key ?? i} className="contents">
            <dt className="text-muted-foreground">{item.term}</dt>
            <dd
              className={cn("min-w-0", item.mono && "font-mono text-xs tabular-nums", item.truncate && "truncate", item.align === "end" && "text-right")}
              title={item.truncate && typeof item.detail === "string" ? item.detail : undefined}
            >
              {item.detail}
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return (
    <dl
      data-slot="description-list"
      data-layout="stacked"
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
          <dd
            className={cn("min-w-0 text-sm", item.mono && "font-mono text-xs", item.truncate && "truncate", item.align === "end" && "text-right")}
            title={item.truncate && typeof item.detail === "string" ? item.detail : undefined}
          >
            {item.detail}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export { DescriptionList, type DescriptionItem, type DescriptionListProps };
