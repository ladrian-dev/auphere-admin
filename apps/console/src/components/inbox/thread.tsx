import { AlertTriangle } from "lucide-react";
import * as React from "react";

import { Button, Skeleton } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { InboxThreadItem } from "@/lib/backend/inbox";

import { eventText } from "./event-text";
import { clock, dayLabel, withDaySeparators } from "./inbox-model";
import { MessageBubble } from "./message-bubble";

/**
 * The messages of one conversation, oldest at the top (spec 030, R8).
 * Messages and what happened to the conversation (the agent asked for
 * help, someone took over…) are interleaved in the order they happened.
 * «Ver mensajes anteriores» pages backwards; a new message scrolls to the
 * bottom only when the reader was already there — never yanks someone who
 * is reading further up.
 */
export function Thread({
  items,
  hasOlder,
  loadingOlder,
  contactInitials,
  now,
  onOlder,
}: {
  items: InboxThreadItem[];
  hasOlder: boolean;
  loadingOlder: boolean;
  contactInitials: string;
  now: Date;
  onOlder: () => void;
}) {
  const t = useT();
  const locale = useLocale();
  const ref = React.useRef<HTMLDivElement>(null);
  const atBottom = React.useRef(true);
  const lastId = items[items.length - 1]?.id;

  React.useLayoutEffect(() => {
    const el = ref.current;
    if (el && atBottom.current) el.scrollTop = el.scrollHeight;
  }, [lastId]);

  const rows = withDaySeparators(items);
  return (
    <div
      ref={ref}
      role="log"
      aria-label={t("inbox.thread")}
      aria-live="polite"
      onScroll={(e) => {
        const el = e.currentTarget;
        atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
      }}
      className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-5 md:px-6"
    >
      {hasOlder ? (
        <Button type="button" variant="ghost" size="sm" className="self-center" disabled={loadingOlder} onClick={onOlder}>
          {t("inbox.thread.older")}
        </Button>
      ) : null}
      {rows.map((row) => {
        if (row.kind === "day") {
          const d = dayLabel(row.at, now, locale);
          return (
            <p key={row.key} className="self-center py-1 text-xs font-medium text-muted-foreground">
              {d.kind === "today" ? t("inbox.time.today") : d.kind === "yesterday" ? t("inbox.time.yesterday") : d.text}
            </p>
          );
        }
        const item = row.item;
        return item.type === "event" ? (
          <EventLine key={row.key} item={item} time={clock(item.at, locale)} />
        ) : (
          <MessageBubble key={row.key} item={item} contactInitials={contactInitials} />
        );
      })}
    </div>
  );
}

/** What happened to the conversation, in its place in the thread. */
function EventLine({ item, time }: { item: InboxThreadItem; time: string }) {
  const t = useT();
  if (item.kind === "escalated") {
    return (
      <p
        role="note"
        className="flex max-w-xl items-start gap-2 self-center rounded-md bg-status-warning-bg px-3 py-2 text-sm text-status-warning-text ring-1 ring-status-warning-border ring-inset"
      >
        <AlertTriangle className="mt-px size-4 shrink-0" aria-hidden="true" />
        <span className="text-pretty">
          {item.detail ? t("inbox.event.escalated.reason", { reason: item.detail }) : t("inbox.event.escalated")} · {time}
        </span>
      </p>
    );
  }
  const text = eventText(item.kind, item.author, item.detail, t);
  return (
    <p className="self-center px-3 text-center text-xs text-muted-foreground text-pretty">
      {text} · {time}
    </p>
  );
}

export function ThreadSkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="flex min-h-0 flex-1 flex-col gap-3 px-4 py-5 md:px-6">
      <Skeleton className="h-10 w-3/5 self-start" />
      <Skeleton className="h-16 w-1/2 self-end" />
      <Skeleton className="h-10 w-2/5 self-start" />
      <Skeleton className="h-12 w-3/5 self-end" />
    </div>
  );
}
