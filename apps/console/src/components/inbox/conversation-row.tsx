import { MessageCircle } from "lucide-react";

import { cn } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { InboxConversation } from "@/lib/backend/inbox";

import { listTime } from "./inbox-model";

/**
 * One conversation in the list (spec 030, R7.1–R7.2). A button: the whole
 * row opens it. Long names and previews are cut with an ellipsis inside the
 * row — never wrapped into a taller row that pushes the list around.
 */
export function ConversationRow({
  conversation: c,
  selected,
  onOpen,
  now,
}: {
  conversation: InboxConversation;
  selected: boolean;
  onOpen: (id: string) => void;
  now: Date;
}) {
  const t = useT();
  const locale = useLocale();
  const last = c.last_message;
  const when = last ? listTime(last.at, now, locale) : null;
  const whenText =
    when === null ? "" : when.kind === "today" ? t("inbox.time.today") : when.kind === "yesterday" ? t("inbox.time.yesterday") : when.text;
  const raw = last ? last.preview || (last.has_media ? t("inbox.row.media") : "") : "";
  const preview = !last
    ? ""
    : last.author.kind === "member" && last.author.is_me
      ? t("inbox.row.you", { text: raw })
      : last.author.kind === "agent"
        ? t("inbox.row.agent", { text: raw })
        : raw;

  return (
    <button
      type="button"
      onClick={() => onOpen(c.id)}
      aria-current={selected ? "true" : undefined}
      className={cn(
        "flex w-full min-w-0 items-start gap-3 border-b border-border-soft px-3 py-3 text-left transition-colors duration-(--duration-fast)",
        "hover:bg-muted focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
        selected && "bg-muted shadow-[inset_2px_0_0_var(--color-primary)]",
      )}
    >
      <span className="relative size-10 shrink-0">
        <span className="grid size-10 place-items-center rounded-full bg-accent-soft text-sm font-semibold text-accent-deep" aria-hidden="true">
          {c.contact.initials}
        </span>
        <span
          className="absolute -right-1 -bottom-1 grid size-5 place-items-center rounded-full bg-card text-primary-text ring-1 ring-border"
          aria-hidden="true"
        >
          <MessageCircle className="size-3" />
        </span>
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex min-w-0 items-baseline justify-between gap-2">
          <span className={cn("min-w-0 truncate text-sm", c.unread ? "font-semibold" : "font-medium")} title={c.contact.name}>
            {c.contact.name}
          </span>
          {whenText ? <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{whenText}</span> : null}
        </span>
        <span className="flex min-w-0 items-center gap-2">
          <span className={cn("min-w-0 flex-1 truncate text-xs", c.unread ? "text-foreground" : "text-muted-foreground")}>
            {preview}
          </span>
          {c.unread ? (
            <span className="size-2 shrink-0 rounded-full bg-primary">
              <span className="sr-only">{t("inbox.row.unread")}</span>
            </span>
          ) : null}
        </span>
        <StateBadges conversation={c} />
      </span>
    </button>
  );
}

function StateBadges({ conversation: c }: { conversation: InboxConversation }) {
  const t = useT();
  const pill = "inline-flex h-5 items-center rounded-full px-2 text-xs leading-none font-medium";
  // Spec 030 (R4.2): with more than one agent, whose number it came in on.
  const agent = c.agent ? (
    <span className={cn(pill, "max-w-40 bg-accent-soft text-accent-deep")} title={c.agent.name}>
      <span className="sr-only">{t("inbox.badge.agent")} </span>
      <span className="truncate">{c.agent.name}</span>
    </span>
  ) : null;
  const state =
    c.state === "waiting" ? (
      <span className={cn(pill, "bg-status-warning-bg text-status-warning-text ring-1 ring-status-warning-border ring-inset")}>
        {t("inbox.badge.waiting")}
      </span>
    ) : c.state === "person" && c.assignee ? (
      <span className={cn(pill, "bg-bg-inverse text-fg-on-dark")}>
        {c.assignee.is_me ? t("inbox.badge.mine") : t("inbox.badge.person", { name: c.assignee.name ?? t("inbox.who.someone") })}
      </span>
    ) : c.state === "resolved" ? (
      <span className={cn(pill, "bg-muted text-muted-foreground")}>{t("inbox.badge.resolved")}</span>
    ) : null;
  if (!state && !agent) return null;
  return (
    <span className="mt-1 flex min-w-0 flex-wrap gap-1">
      {state}
      {agent}
    </span>
  );
}
