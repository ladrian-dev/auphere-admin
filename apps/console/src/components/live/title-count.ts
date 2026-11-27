import * as React from "react";

const PREFIX = /^\(\d+\+?\) /;

/** «(3) Reservas · Auphere» — the count first, `99+` from 100, none at zero (R3.6). */
export function withCount(title: string, n: number): string {
  const bare = title.replace(PREFIX, "");
  if (n <= 0) return bare;
  return `(${n > 99 ? "99+" : n}) ${bare}`;
}

/**
 * Keep the unread count at the head of the tab's title on every screen. Next
 * writes a new title on each navigation; an observer on `<head>` puts the count
 * back. Setting the same title again is a no-op, so it does not loop.
 */
export function useTitleCount(n: number): void {
  React.useEffect(() => {
    if (typeof document === "undefined") return;
    const apply = () => {
      const next = withCount(document.title, n);
      if (next !== document.title) document.title = next;
    };
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.head, { subtree: true, childList: true, characterData: true });
    return () => {
      observer.disconnect();
      const bare = withCount(document.title, 0);
      if (bare !== document.title) document.title = bare;
    };
  }, [n]);
}
