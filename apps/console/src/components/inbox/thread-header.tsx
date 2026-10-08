import { ArrowLeft, Check, Mail, PanelRight, RotateCcw } from "lucide-react";

import { Button, cn } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { InboxDetail } from "@/lib/backend/inbox";

/**
 * The top of an open conversation (spec 030, R9, R12): who it is, who
 * answers now, and the three actions that do not need the composer —
 * mark as unread, resolve / reopen, show the contact panel. Icon buttons
 * carry their name for assistive tech and as a `title` for the eye.
 */
export function ThreadHeader({
  detail,
  initials,
  busy,
  panelOpen,
  onBack,
  onUnread,
  onResolve,
  onReopen,
  onTogglePanel,
}: {
  detail: InboxDetail;
  initials: string;
  busy: boolean;
  panelOpen: boolean;
  onBack: () => void;
  onUnread: () => void;
  onResolve: () => void;
  onReopen: () => void;
  onTogglePanel: () => void;
}) {
  const t = useT();
  const resolved = detail.state === "resolved";
  // Spec 030: with more than one agent, the one of this number by name.
  const attends =
    detail.state === "agent"
      ? detail.agent
        ? t("inbox.assigned", { name: detail.agent.name })
        : t("inbox.assigned.agent")
      : detail.assignee
        ? detail.assignee.is_me
          ? t("inbox.assigned.you")
          : t("inbox.assigned", { name: detail.assignee.name ?? t("inbox.who.someone") })
        : detail.state === "waiting"
          ? t("inbox.assigned.nobody")
          : t("inbox.assigned.agent");

  return (
    <div className="flex items-center gap-3 border-b border-border px-4 py-3">
      <Button type="button" variant="ghost" size="icon" className="md:hidden" onClick={onBack} aria-label={t("inbox.back")}>
        <ArrowLeft />
      </Button>
      <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-full bg-accent-soft text-sm font-semibold text-accent-deep">
        {initials}
      </span>
      <div className="flex min-w-0 flex-1 flex-col">
        <h2 className="truncate text-base font-semibold" title={detail.contact.name}>
          {detail.contact.name}
        </h2>
        <span className="truncate text-xs font-medium text-muted-foreground" title={attends}>
          {attends}
        </span>
      </div>
      <div className="flex shrink-0 gap-2">
        <IconAction label={t("inbox.action.unread")} disabled={busy} onClick={onUnread}>
          <Mail />
        </IconAction>
        {resolved ? (
          <IconAction label={t("inbox.action.reopen")} disabled={busy} onClick={onReopen}>
            <RotateCcw />
          </IconAction>
        ) : (
          <IconAction label={t("inbox.action.resolve")} disabled={busy} onClick={onResolve}>
            <Check />
          </IconAction>
        )}
        <IconAction
          label={panelOpen ? t("inbox.action.panel.hide") : t("inbox.action.panel")}
          pressed={panelOpen}
          onClick={onTogglePanel}
        >
          <PanelRight />
        </IconAction>
      </div>
    </div>
  );
}

function IconAction({
  label,
  disabled,
  pressed,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  pressed?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      className={cn(pressed && "bg-muted")}
    >
      {children}
    </Button>
  );
}
