"use client";

import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { Loader2, SearchIcon } from "lucide-react";
import * as React from "react";

import { cn } from "../lib/utils";
import { Kbd } from "./kbd";

/**
 * Command palette (⌘K). A dialog with a combobox: the input owns the
 * keyboard (↑↓ move, ↵ run, Esc close), the list is a `listbox` of grouped
 * `option`s. Async-friendly: the host passes `items` for the current query
 * plus `loading` / `error`; the palette renders the five states.
 *
 * Headless about data on purpose — the console decides what a query means
 * (clients, actions, pages) and the palette only renders and navigates.
 */
export type CommandItem = {
  id: string;
  /** Group heading key — items with the same group render together. */
  group: string;
  label: string;
  /** Secondary text (mono, muted). */
  hint?: string;
  icon?: React.ReactNode;
  /** Right-aligned shortcut / badge. */
  trailing?: React.ReactNode;
  onSelect: () => void;
  /** Extra tokens matched by the local filter (ref, slug…). */
  keywords?: string;
};

export type CommandPaletteProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  query: string;
  onQueryChange: (q: string) => void;
  items: CommandItem[];
  /** Ordered group ids → visible label. Groups not listed render last, in first-seen order. */
  groups?: Record<string, string>;
  loading?: boolean;
  error?: React.ReactNode;
  /** Empty-state message; receives the current query. */
  emptyMessage?: (q: string) => React.ReactNode;
  title: string;
  placeholder?: string;
  hint?: React.ReactNode;
  className?: string;
};

function CommandPalette({
  open,
  onOpenChange,
  query,
  onQueryChange,
  items,
  groups,
  loading,
  error,
  emptyMessage,
  title,
  placeholder,
  hint,
  className,
}: CommandPaletteProps) {
  const listId = React.useId();
  const [active, setActive] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Keep the active index inside the list when items change.
  React.useEffect(() => {
    setActive((a) => (items.length === 0 ? 0 : Math.min(a, items.length - 1)));
  }, [items]);
  React.useEffect(() => {
    if (open) setActive(0);
  }, [open, query]);

  const ordered = React.useMemo(() => {
    const order = groups ? Object.keys(groups) : [];
    const seen: string[] = [];
    for (const it of items) if (!order.includes(it.group) && !seen.includes(it.group)) seen.push(it.group);
    const all = [...order, ...seen];
    return all
      .map((g) => ({ id: g, label: groups?.[g] ?? g, items: items.filter((i) => i.group === g) }))
      .filter((g) => g.items.length > 0);
  }, [items, groups]);
  const flat = React.useMemo(() => ordered.flatMap((g) => g.items), [ordered]);
  const activeItem = flat[active];

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (flat.length ? (a + 1) % flat.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (flat.length ? (a - 1 + flat.length) % flat.length : 0));
    } else if (e.key === "Home") {
      e.preventDefault();
      setActive(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActive(Math.max(flat.length - 1, 0));
    } else if (e.key === "Enter") {
      if (activeItem) {
        e.preventDefault();
        activeItem.onSelect();
        onOpenChange(false);
      }
    }
  }

  React.useEffect(() => {
    if (!activeItem) return;
    const el = document.getElementById(`${listId}-${activeItem.id}`);
    if (el && typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "nearest" });
  }, [activeItem, listId]);

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop className="fixed inset-0 isolate z-50 bg-black/10 duration-100 supports-backdrop-filter:backdrop-blur-xs data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0" />
        <DialogPrimitive.Popup
          data-slot="command-palette"
          initialFocus={inputRef}
          className={cn(
            "fixed top-[12svh] left-1/2 z-50 flex w-full max-w-[calc(100%-2rem)] -translate-x-1/2 flex-col overflow-hidden rounded-md bg-popover text-sm text-popover-foreground ring-1 ring-foreground/10 duration-100 outline-none sm:max-w-xl data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95",
            className,
          )}
        >
          <DialogPrimitive.Title className="sr-only">{title}</DialogPrimitive.Title>
          <div className="flex items-center gap-2 border-b border-border px-3">
            {loading ? (
              <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" aria-hidden="true" />
            ) : (
              <SearchIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            )}
            <input
              ref={inputRef}
              role="combobox"
              aria-expanded="true"
              aria-controls={listId}
              aria-activedescendant={activeItem ? `${listId}-${activeItem.id}` : undefined}
              aria-autocomplete="list"
              aria-label={title}
              autoComplete="off"
              spellCheck={false}
              value={query}
              placeholder={placeholder}
              onChange={(e) => onQueryChange(e.target.value)}
              onKeyDown={onKeyDown}
              className="h-11 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
            <Kbd>Esc</Kbd>
          </div>
          <div id={listId} role="listbox" aria-label={title} aria-busy={loading || undefined} className="max-h-[50svh] overflow-y-auto p-2">
            {error ? (
              <p role="alert" className="px-2 py-6 text-center text-sm text-destructive text-pretty">
                {error}
              </p>
            ) : flat.length === 0 ? (
              <p role="status" className="px-2 py-6 text-center text-sm text-muted-foreground text-pretty">
                {loading ? null : emptyMessage ? emptyMessage(query) : "—"}
              </p>
            ) : (
              ordered.map((g) => (
                <div key={g.id} role="group" aria-labelledby={`${listId}-g-${g.id}`} className="mb-2 last:mb-0">
                  <p id={`${listId}-g-${g.id}`} className="px-2 py-1 font-mono text-xs tracking-eyebrow text-muted-foreground uppercase">
                    {g.label}
                  </p>
                  {g.items.map((it) => {
                    const idx = flat.indexOf(it);
                    const isActive = idx === active;
                    return (
                      <div
                        key={it.id}
                        id={`${listId}-${it.id}`}
                        role="option"
                        aria-selected={isActive}
                        data-active={isActive || undefined}
                        onMouseEnter={() => setActive(idx)}
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => {
                          it.onSelect();
                          onOpenChange(false);
                        }}
                        className={cn(
                          "flex min-w-0 cursor-pointer items-center gap-3 rounded-sm px-2 py-2",
                          isActive ? "bg-muted text-foreground" : "text-foreground/90",
                        )}
                      >
                        {it.icon ? <span className="grid size-4 shrink-0 place-items-center text-muted-foreground [&>svg]:size-4">{it.icon}</span> : null}
                        <span className="min-w-0 flex-1 truncate" title={it.label}>
                          {it.label}
                        </span>
                        {it.hint ? (
                          <span className="min-w-0 max-w-[40%] truncate font-mono text-xs text-muted-foreground" title={it.hint}>
                            {it.hint}
                          </span>
                        ) : null}
                        {it.trailing ? <span className="shrink-0">{it.trailing}</span> : null}
                      </div>
                    );
                  })}
                </div>
              ))
            )}
          </div>
          {hint ? <div className="border-t border-border px-3 py-2 font-mono text-xs text-muted-foreground">{hint}</div> : null}
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

/** Local filter helper: case/diacritic-insensitive substring over label + keywords. */
function filterCommandItems<T extends Pick<CommandItem, "label" | "keywords">>(items: T[], query: string): T[] {
  const q = fold(query);
  if (!q) return items;
  return items.filter((i) => fold(`${i.label} ${i.keywords ?? ""}`).includes(q));
}
function fold(s: string) {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

export { CommandPalette, filterCommandItems };
