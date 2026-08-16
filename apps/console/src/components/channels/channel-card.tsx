"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { StatusBadge, formatDateTime } from "@nexus/ui";

import { setChannelRoleAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useLocale, useT } from "@/i18n/client";
import type { ChannelDetail, ChannelRole } from "@/lib/backend/channels";

import { SELECT_CLASS } from "./whatsapp-connect";

const TONE = { active: "positive", paused: "warning", degraded: "warning", disconnected: "danger" } as const;
const QUALITY_TONE = { GREEN: "positive", YELLOW: "warning", RED: "danger" } as const;

/** Pure: which tone a Meta quality rating maps to. */
export function qualityTone(rating: string | null): "positive" | "warning" | "danger" | "muted" {
  return (rating && QUALITY_TONE[rating as keyof typeof QUALITY_TONE]) || "muted";
}

export function ChannelCard({ refId, channel, manage, showRoles }: { refId: string; channel: ChannelDetail; manage: boolean; showRoles: boolean }) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const rating = (channel.quality_rating ?? "UNKNOWN").toUpperCase();
  const qualityKey = (["GREEN", "YELLOW", "RED"].includes(rating) ? `ch.quality.${rating}` : "ch.quality.UNKNOWN") as "ch.quality.GREEN";
  const roleId = `role-${channel.id}`;

  function changeRole(value: string) {
    const role = (value === "" ? null : value) as ChannelRole | null;
    startTransition(async () => {
      const res = await setChannelRoleAction({ ref: refId, channelId: channel.id, role });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("ch.role.saved"));
      router.refresh();
    });
  }

  return (
    <li className="flex min-w-0 flex-col gap-3 rounded-md bg-card p-4 ring-1 ring-foreground/10" aria-busy={pending}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">{channel.type === "whatsapp" ? t("ch.card.whatsapp") : channel.type}</span>
        <StatusBadge tone={TONE[channel.status as keyof typeof TONE] ?? "muted"}>{t(`status.${channel.status}` as "status.active")}</StatusBadge>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted-foreground">{t("ch.card.number")}</dt>
        <dd className="min-w-0 truncate font-mono" title={channel.provider_identifier}>
          {channel.provider_identifier}
        </dd>
        {channel.verified_name ? (
          <>
            <dt className="text-muted-foreground">{t("ch.card.name")}</dt>
            <dd className="min-w-0 truncate" title={channel.verified_name}>
              {channel.verified_name}
            </dd>
          </>
        ) : null}
        <dt className="text-muted-foreground">{t("ch.card.quality")}</dt>
        <dd>
          <StatusBadge tone={qualityTone(channel.quality_rating)}>{t(qualityKey)}</StatusBadge>
        </dd>
        <dt className="text-muted-foreground">{t("ch.card.tier")}</dt>
        <dd className="font-mono text-xs">{channel.messaging_tier ?? "—"}</dd>
        {channel.mode ? (
          <>
            <dt className="text-muted-foreground">{t("ch.card.mode")}</dt>
            <dd className="font-mono text-xs">{channel.mode}</dd>
          </>
        ) : null}
        <dt className="text-muted-foreground">{t("ch.card.role")}</dt>
        <dd>
          {manage && showRoles && channel.type === "whatsapp" ? (
            <>
              <label htmlFor={roleId} className="sr-only">
                {t("ch.card.role")}
              </label>
              <select id={roleId} className={SELECT_CLASS} value={channel.role ?? ""} onChange={(e) => changeRole(e.target.value)} disabled={pending}>
                <option value="">{t("ch.role.none")}</option>
                <option value="agent">{t("ch.role.agent")}</option>
                <option value="notifications">{t("ch.role.notifications")}</option>
              </select>
            </>
          ) : (
            <span>{channel.role ? t(`ch.role.${channel.role}` as "ch.role.agent") : t("ch.role.none")}</span>
          )}
        </dd>
        <dt className="text-muted-foreground">{t("ch.card.health")}</dt>
        <dd className="tabular-nums">{channel.last_health_check_at ? formatDateTime(channel.last_health_check_at, locale) : t("ch.card.never")}</dd>
        <dt className="text-muted-foreground">{t("common.created")}</dt>
        <dd className="tabular-nums">{formatDateTime(channel.created_at, locale)}</dd>
      </dl>
    </li>
  );
}
