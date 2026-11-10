"use client";

import { AtSign, MessagesSquare, MoreHorizontal } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  ConfirmDialog,
  DescriptionList,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  StatusBadge,
  formatDateTime,
} from "@nexus/ui";

import { disconnectChannelAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { ChannelDetail } from "@/lib/backend/channels";

const TONE = { active: "positive", paused: "warning", degraded: "warning", disconnected: "danger" } as const;

/** Why the channel needs attention, in words, with the step to take. */
export const ATTENTION: Record<string, MessageKey> = {
  token_revoked: "ch.social.attention.token_revoked",
  permission_lost: "ch.social.attention.permission_lost",
  messages_disabled: "ch.social.attention.messages_disabled",
  subscribe_failed: "ch.social.attention.subscribe_failed",
  no_credentials: "ch.social.attention.token_revoked",
};

/** The account or Page as the business knows it. */
export function metaSocialName(channel: ChannelDetail): string {
  if (channel.username) return `@${channel.username}`;
  return channel.display_name ?? channel.provider_identifier;
}

/**
 * Spec 049 — an Instagram account or a Facebook Page. Same reading as the
 * WhatsApp card (icon, name, state, one action), without what only WhatsApp
 * has: quality, tier, catalogue, roles, templates.
 */
export function MetaSocialCard({ refId, channel, manage }: { refId: string; channel: ChannelDetail; manage: boolean }) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [confirm, setConfirm] = React.useState(false);
  const instagram = channel.type === "instagram";
  const name = metaSocialName(channel);
  const gone = channel.status === "disconnected";
  const Icon = instagram ? AtSign : MessagesSquare;
  const attention = channel.needs_attention ? (ATTENTION[channel.needs_attention] ?? "ch.social.attention.subscribe_failed") : null;

  function disconnect() {
    startTransition(async () => {
      const res = await disconnectChannelAction({ ref: refId, channelId: channel.id });
      if (!res.ok) return void toast.error(res.message);
      setConfirm(false);
      toast.success(t("ch.social.disconnect.done", { name }));
      router.refresh();
    });
  }

  return (
    <li className="flex min-w-0 flex-col gap-3 rounded-md bg-card p-4 ring-1 ring-foreground/10" aria-busy={pending}>
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted ring-1 ring-foreground/10">
            <Icon aria-hidden="true" className="size-5 text-muted-foreground" />
          </span>
          <div className="flex min-w-0 flex-col">
            <span className="truncate font-medium">{name}</span>
            <span className="truncate text-xs text-muted-foreground">
              {t(instagram ? "ch.social.card.instagram" : "ch.social.card.messenger")}
              {channel.username && channel.display_name ? ` · ${channel.display_name}` : ""}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <StatusBadge tone={TONE[channel.status as keyof typeof TONE] ?? "muted"}>
            {t(`status.${channel.status}` as "status.active")}
          </StatusBadge>
          {manage && !gone ? (
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button variant="ghost" size="icon-sm" disabled={pending} aria-label={t("ch.card.actions", { number: name })}>
                    <MoreHorizontal aria-hidden="true" />
                  </Button>
                }
              />
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuItem variant="destructive" onClick={() => setConfirm(true)}>
                  <span className="flex flex-col">
                    {t("ch.social.disconnect")}
                    <span className="text-xs">{t("ch.disconnect.why")}</span>
                  </span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </div>

      {instagram && !gone ? (
        <DescriptionList
          layout="inline"
          dense
          items={[
            {
              key: "comments",
              term: t("ch.social.card.comments"),
              detail: <span>{t(channel.comments_enabled === false ? "ch.social.card.comments.off" : "ch.social.card.comments.on")}</span>,
            },
          ]}
        />
      ) : null}

      {attention && !gone ? (
        <Callout tone="warning" title={t("ch.social.attention.title")}>
          {t(attention)}
        </Callout>
      ) : null}

      <p className="text-xs text-muted-foreground tabular-nums">
        {t("ch.card.health")}: {channel.last_health_check_at ? formatDateTime(channel.last_health_check_at, locale) : t("ch.card.never")}
        {" · "}
        {t("common.created")}: {formatDateTime(channel.created_at, locale)}
      </p>

      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={t("ch.social.disconnect.title", { name })}
        description={t("ch.social.disconnect.body")}
        confirmLabel={t("ch.social.disconnect.confirm")}
        cancelLabel={t("common.cancel")}
        destructive
        onConfirm={async () => disconnect()}
      />
    </li>
  );
}
