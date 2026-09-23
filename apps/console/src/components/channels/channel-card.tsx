"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { DescriptionList, NativeSelect, StatusBadge, formatDateTime } from "@nexus/ui";

import { setChannelRoleAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useLocale, useT } from "@/i18n/client";
import type { ChannelDetail, ChannelRole } from "@/lib/backend/channels";


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
      <DescriptionList
        layout="inline"
        dense
        items={[
          { key: "number", term: t("ch.card.number"), detail: channel.provider_identifier, mono: true, truncate: true },
          ...(channel.verified_name ? [{ key: "name", term: t("ch.card.name"), detail: channel.verified_name, truncate: true }] : []),
          { key: "quality", term: t("ch.card.quality"), detail: <StatusBadge tone={qualityTone(channel.quality_rating)}>{t(qualityKey)}</StatusBadge> },
          { key: "tier", term: t("ch.card.tier"), detail: channel.messaging_tier ?? "—", mono: true },
          ...(channel.mode ? [{ key: "mode", term: t("ch.card.mode"), detail: channel.mode, mono: true }] : []),
          {
            key: "role",
            term: t("ch.card.role"),
            detail:
              manage && showRoles && channel.type === "whatsapp" ? (
                <>
                  <label htmlFor={roleId} className="sr-only">
                    {t("ch.card.role")}
                  </label>
                  <NativeSelect id={roleId} wrapperClassName="w-full" value={channel.role ?? ""} onChange={(e) => changeRole(e.target.value)} disabled={pending}>
                    <option value="">{t("ch.role.none")}</option>
                    <option value="agent">{t("ch.role.agent")}</option>
                    <option value="notifications">{t("ch.role.notifications")}</option>
                  </NativeSelect>
                </>
              ) : (
                <span>{channel.role ? t(`ch.role.${channel.role}` as "ch.role.agent") : t("ch.role.none")}</span>
              ),
          },
          { key: "health", term: t("ch.card.health"), detail: <span className="tabular-nums">{channel.last_health_check_at ? formatDateTime(channel.last_health_check_at, locale) : t("ch.card.never")}</span> },
          { key: "created", term: t("common.created"), detail: <span className="tabular-nums">{formatDateTime(channel.created_at, locale)}</span> },
        ]}
      />
    </li>
  );
}
