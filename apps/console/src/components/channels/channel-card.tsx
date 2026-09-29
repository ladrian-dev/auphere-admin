"use client";

import { MoreHorizontal } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  ConfirmDialog,
  DescriptionList,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  HelpHint,
  NativeSelect,
  StatusBadge,
  formatDateTime,
} from "@nexus/ui";

import { disconnectChannelAction, setChannelRoleAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useLocale, useT } from "@/i18n/client";
import { messages, type MessageKey } from "@/i18n/messages";
import type { ChannelDetail, ChannelRole } from "@/lib/backend/channels";

const TONE = { active: "positive", paused: "warning", degraded: "warning", disconnected: "danger" } as const;
const QUALITY_TONE = { GREEN: "positive", YELLOW: "warning", RED: "danger" } as const;

/** Pure: which tone a Meta quality rating maps to. */
export function qualityTone(rating: string | null): "positive" | "warning" | "danger" | "muted" {
  return (rating && QUALITY_TONE[rating as keyof typeof QUALITY_TONE]) || "muted";
}

/**
 * El límite de Meta, en conversaciones.
 *
 * La API devuelve `TIER_250`, que no dice ni que son conversaciones ni que el
 * límite es diario ni que solo cuenta iniciar. Un tier que el catálogo de Meta
 * añada mañana cae en su propia clave y se enseña tal cual antes que mentir.
 */
export function tierKey(tier: string | null): MessageKey | null {
  if (!tier) return null;
  const key = `ch.tier.${tier.toUpperCase()}` as MessageKey;
  return key in messages ? key : null;
}

export function ChannelCard({
  refId,
  channel,
  manage,
  showRoles,
}: {
  refId: string;
  channel: ChannelDetail;
  manage: boolean;
  showRoles: boolean;
}) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [confirmarSoltar, setConfirmarSoltar] = React.useState(false);
  const rating = (channel.quality_rating ?? "UNKNOWN").toUpperCase();
  const qualityKey = (["GREEN", "YELLOW", "RED"].includes(rating) ? `ch.quality.${rating}` : "ch.quality.UNKNOWN") as "ch.quality.GREEN";
  const roleId = `role-${channel.id}`;
  const suelto = channel.status === "disconnected";
  const tier = tierKey(channel.messaging_tier);

  function changeRole(value: string) {
    const role = (value === "" ? null : value) as ChannelRole | null;
    startTransition(async () => {
      const res = await setChannelRoleAction({ ref: refId, channelId: channel.id, role });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("ch.role.saved"));
      router.refresh();
    });
  }

  function soltar() {
    startTransition(async () => {
      const res = await disconnectChannelAction({ ref: refId, channelId: channel.id });
      if (!res.ok) return void toast.error(res.message);
      setConfirmarSoltar(false);
      toast.success(t("ch.disconnect.done", { number: channel.provider_identifier }));
      router.refresh();
    });
  }

  return (
    <li className="flex min-w-0 flex-col gap-3 rounded-md bg-card p-4 ring-1 ring-foreground/10" aria-busy={pending}>
      {/* El número arriba y grande: es lo que el partner reconoce. «WhatsApp»
          lo sabe por el sitio donde está mirando. */}
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-col">
          <span className="truncate font-medium tabular-nums">{channel.provider_identifier}</span>
          <span className="truncate text-xs text-muted-foreground">
            {channel.type === "whatsapp" ? t("ch.card.whatsapp") : channel.type}
            {channel.verified_name ? ` · ${channel.verified_name}` : ""}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <StatusBadge tone={TONE[channel.status as keyof typeof TONE] ?? "muted"}>
            {t(`status.${channel.status}` as "status.active")}
          </StatusBadge>
          {/* Se podía conectar un número y no soltarlo: desvincular no existía
              ni en la API. Un producto donde se entra y no se sale da más
              miedo al entrar del que debería. */}
          {manage && !suelto ? (
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    disabled={pending}
                    aria-label={t("ch.card.actions", { number: channel.provider_identifier })}
                  >
                    <MoreHorizontal aria-hidden="true" />
                  </Button>
                }
              />
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuItem variant="destructive" onClick={() => setConfirmarSoltar(true)}>
                  <span className="flex flex-col">
                    {t("ch.disconnect")}
                    <span className="text-xs">{t("ch.disconnect.why")}</span>
                  </span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </div>

      <DescriptionList
        layout="inline"
        dense
        items={[
          ...(channel.quality_rating
            ? [
                {
                  key: "quality",
                  term: t("ch.card.quality"),
                  detail: <StatusBadge tone={qualityTone(channel.quality_rating)}>{t(qualityKey)}</StatusBadge>,
                },
              ]
            : []),
          ...(tier
            ? [
                {
                  key: "tier",
                  term: t("ch.card.tier"),
                  detail: (
                    <span className="inline-flex items-center gap-1">
                      {t(tier)}
                      <HelpHint label={t("ch.card.tier")}>{t("ch.tier.help")}</HelpHint>
                    </span>
                  ),
                },
              ]
            : []),
          ...(manage && showRoles && channel.type === "whatsapp" && !suelto
            ? [
                {
                  key: "role",
                  term: t("ch.card.role"),
                  detail: (
                    <>
                      <label htmlFor={roleId} className="sr-only">
                        {t("ch.card.role")}
                      </label>
                      <NativeSelect
                        id={roleId}
                        wrapperClassName="w-full"
                        value={channel.role ?? ""}
                        onChange={(e) => changeRole(e.target.value)}
                        disabled={pending}
                      >
                        <option value="">{t("ch.role.none")}</option>
                        <option value="agent">{t("ch.role.agent")}</option>
                        <option value="notifications">{t("ch.role.notifications")}</option>
                      </NativeSelect>
                    </>
                  ),
                },
              ]
            : channel.role
              ? [{ key: "role", term: t("ch.card.role"), detail: <span>{t(`ch.role.${channel.role}` as "ch.role.agent")}</span> }]
              : []),
        ]}
      />

      {/* Las fechas, al pie y en gris: se miran cuando algo va mal, no cuando
          todo va bien. Antes pesaban lo mismo que el número. */}
      <p className="text-xs text-muted-foreground tabular-nums">
        {t("ch.card.health")}:{" "}
        {channel.last_health_check_at ? formatDateTime(channel.last_health_check_at, locale) : t("ch.card.never")}
        {" · "}
        {t("common.created")}: {formatDateTime(channel.created_at, locale)}
      </p>

      <ConfirmDialog
        open={confirmarSoltar}
        onOpenChange={setConfirmarSoltar}
        title={t("ch.disconnect.title", { number: channel.provider_identifier })}
        description={t("ch.disconnect.body")}
        confirmLabel={t("ch.disconnect.confirm")}
        cancelLabel={t("common.cancel")}
        destructive
        onConfirm={async () => soltar()}
      />
    </li>
  );
}
