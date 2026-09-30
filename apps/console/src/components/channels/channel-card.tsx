"use client";

import { MessageCircle, MoreHorizontal } from "lucide-react";
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
  HelpHint,
  NativeSelect,
  StatusBadge,
  StatusDot,
  formatDateTime,
} from "@nexus/ui";

import { clearCatalogAction, disconnectChannelAction, setChannelRoleAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useLocale, useT } from "@/i18n/client";
import { messages, type MessageKey } from "@/i18n/messages";
import type { ChannelDetail, ChannelRole } from "@/lib/backend/channels";

import { CatalogPicker, catalogFailureKey } from "./catalog-picker";

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

/**
 * Pure: which sentence the unlink dialog shows. A number in coexistence
 * keeps chatting from its phone after we deregister it (R2.5); the dialog
 * has to say so, or «unlink» reads as «leave it without WhatsApp».
 */
export function disconnectBodyKey(mode: string | null): MessageKey {
  return mode === "coexistence" ? "ch.disconnect.body.coexistence" : "ch.disconnect.body";
}

const PENDING_STEP: Record<string, MessageKey> = { deregister: "ch.pending.deregister", unsubscribe: "ch.pending.unsubscribe" };

/**
 * El icono de la aplicación del canal, con su estado en la esquina.
 *
 * Se pide a nuestro propio origen: la consola publica `img-src 'self'`, así
 * que una imagen del dominio del proveedor no cargaría — es el mismo fallo
 * que tenían los conectores. Sin logotipo, un icono de conversación sobre un
 * cuadro tintado; un hueco gris no distingue una tarjeta de otra.
 */
function ChannelIcon({ refId, channel }: { refId: string; channel: ChannelDetail }) {
  return (
    <span data-slot="channel-icon" className="relative shrink-0">
      <span className="flex size-10 items-center justify-center overflow-hidden rounded-md bg-muted ring-1 ring-foreground/10">
        {channel.logo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={`/api/channel-logo/${encodeURIComponent(refId)}/${encodeURIComponent(channel.id)}`}
            alt=""
            loading="lazy"
            className="size-10 object-contain"
          />
        ) : (
          <MessageCircle aria-hidden="true" className="size-5 text-muted-foreground" />
        )}
      </span>
    </span>
  );
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
  const [elegirCatalogo, setElegirCatalogo] = React.useState(false);
  const [confirmarQuitarCatalogo, setConfirmarQuitarCatalogo] = React.useState(false);
  const rating = (channel.quality_rating ?? "UNKNOWN").toUpperCase();
  const qualityKey = (["GREEN", "YELLOW", "RED"].includes(rating) ? `ch.quality.${rating}` : "ch.quality.UNKNOWN") as "ch.quality.GREEN";
  const roleId = `role-${channel.id}`;
  const suelto = channel.status === "disconnected";
  const tier = tierKey(channel.messaging_tier);
  // Un paso que la API añada mañana se enseña por su nombre antes que callarlo.
  const pendientes = (channel.unlink_pending ?? []).map((step) => (PENDING_STEP[step] ? t(PENDING_STEP[step]) : step));

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
      // Desvincular nunca falla por Meta: el canal queda suelto igual y lo
      // que Meta no aceptó viene en `unlink_pending`. El aviso lo dice ya,
      // en vez de dejar que la tarjeta lo cuente al recargar.
      toast.success(t("ch.disconnect.done", { number: channel.provider_identifier }));
      if (res.data.unlink_pending.length > 0) toast.warning(t("ch.pending.still"));
      router.refresh();
    });
  }

  function quitarCatalogo() {
    startTransition(async () => {
      const res = await clearCatalogAction({ ref: refId, channelId: channel.id });
      if (!res.ok) return void toast.error(res.message);
      setConfirmarQuitarCatalogo(false);
      if (res.data.catalog_error) {
        const key = catalogFailureKey(res.data.catalog_error.code);
        toast.error(key ? t(key, { message: res.data.catalog_error.message ?? "" }) : t("common.error.backend"));
      } else toast.success(t("ch.catalog.cleared"));
      router.refresh();
    });
  }

  // El mismo endpoint termina lo que quedó pendiente: sin pasos repetidos,
  // y sin un segundo verbo que el partner tenga que aprender.
  function reintentar() {
    startTransition(async () => {
      const res = await disconnectChannelAction({ ref: refId, channelId: channel.id });
      if (!res.ok) return void toast.error(res.message);
      if (res.data.unlink_pending.length > 0) toast.warning(t("ch.pending.still"));
      else toast.success(t("ch.pending.done"));
      router.refresh();
    });
  }

  return (
    <li className="flex min-w-0 flex-col gap-3 rounded-md bg-card p-4 ring-1 ring-foreground/10" aria-busy={pending}>
      {/* Icono, número, estado y una acción — la misma lectura que una
          tarjeta de conector, porque son la misma clase de cosa: algo de
          fuera que el agente usa. El número va de cabecera porque es lo que
          el partner reconoce; «WhatsApp» ya lo dice el icono. */}
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-3">
          <ChannelIcon refId={refId} channel={channel} />
          <div className="flex min-w-0 flex-col">
            <span className="truncate font-medium tabular-nums">{channel.provider_identifier}</span>
            <span className="truncate text-xs text-muted-foreground">
              {channel.type === "whatsapp" ? t("ch.card.whatsapp") : channel.type}
              {channel.verified_name ? ` · ${channel.verified_name}` : ""}
            </span>
          </div>
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
                  // Un punto y una palabra, **no** otra pastilla: la tarjeta
                  // tenía dos insignias iguales —«Activo» y «Alta»— y se
                  // leían como dos estados del canal. Solo una lo es. La
                  // calidad es una propiedad que Meta mide.
                  detail: (
                    <span className="inline-flex items-center gap-2">
                      <StatusDot tone={qualityTone(channel.quality_rating)} label={t(qualityKey)} />
                      {t(qualityKey)}
                    </span>
                  ),
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
          ...(channel.type === "whatsapp" && !suelto
            ? [
                {
                  key: "catalog",
                  term: t("ch.catalog"),
                  // Spec 022: la tarjeta dice la verdad de Meta sobre el
                  // catálogo, y solo ofrece lo que quien mira puede hacer.
                  detail: <CatalogRow channel={channel} manage={manage} pending={pending} onConnect={() => setElegirCatalogo(true)} onClear={() => setConfirmarQuitarCatalogo(true)} />,
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

      {/* R3.2: lo que Meta no aceptó se ve aquí, con su reintento. Sin esto
          la tarjeta diría «desvinculado» de un número que Meta aún tiene
          registrado bajo nuestra aplicación — a medias, y en silencio. */}
      {suelto && pendientes.length > 0 ? (
        <Callout
          tone="warning"
          title={t("ch.pending.title")}
          action={
            manage ? (
              <Button type="button" size="sm" variant="outline" onClick={reintentar} disabled={pending}>
                {t("ch.pending.retry")}
              </Button>
            ) : null
          }
        >
          {t("ch.pending.body", { steps: pendientes.join(t("ch.pending.and")) })}
        </Callout>
      ) : null}

      {/* Las fechas, al pie y en gris: se miran cuando algo va mal, no cuando
          todo va bien. Antes pesaban lo mismo que el número. */}
      <p className="text-xs text-muted-foreground tabular-nums">
        {t("ch.card.health")}:{" "}
        {channel.last_health_check_at ? formatDateTime(channel.last_health_check_at, locale) : t("ch.card.never")}
        {" · "}
        {t("common.created")}: {formatDateTime(channel.created_at, locale)}
      </p>

      {channel.type === "whatsapp" && !suelto ? (
        <>
          <CatalogPicker refId={refId} channelId={channel.id} current={channel.catalog} open={elegirCatalogo} onOpenChange={setElegirCatalogo} />
          <ConfirmDialog
            open={confirmarQuitarCatalogo}
            onOpenChange={setConfirmarQuitarCatalogo}
            title={t("ch.catalog.clear.title", { name: channel.catalog?.name ?? channel.catalog?.id ?? "" })}
            description={t("ch.catalog.clear.body")}
            confirmLabel={t("ch.catalog.clear")}
            cancelLabel={t("common.cancel")}
            destructive
            onConfirm={async () => quitarCatalogo()}
          />
        </>
      ) : null}

      <ConfirmDialog
        open={confirmarSoltar}
        onOpenChange={setConfirmarSoltar}
        title={t("ch.disconnect.title", { number: channel.provider_identifier })}
        description={t(disconnectBodyKey(channel.mode))}
        confirmLabel={t("ch.disconnect.confirm")}
        cancelLabel={t("common.cancel")}
        destructive
        onConfirm={async () => soltar()}
      />
    </li>
  );
}

/**
 * La fila «Catálogo» de la tarjeta, por estado (spec 022, data-model):
 * ninguno · conectado · sin permiso · sin comprobar · solo lectura. Un estado
 * que la API añada mañana cae en «ninguno» con el nombre si lo hay, nunca en
 * un hueco.
 */
export function CatalogRow({
  channel,
  manage,
  pending,
  onConnect,
  onClear,
}: {
  channel: ChannelDetail;
  manage: boolean;
  pending: boolean;
  onConnect: () => void;
  onClear: () => void;
}) {
  const t = useT();
  const name = channel.catalog?.name ?? channel.catalog?.id ?? null;
  const errorKey = channel.catalog_error ? catalogFailureKey(channel.catalog_error.code) : null;
  if (channel.catalog_state === "permission_missing") {
    return <span className="text-sm text-muted-foreground">{t("ch.catalog.permission")}</span>;
  }
  return (
    <span data-slot="catalog-row" data-state={channel.catalog_state} className="flex min-w-0 flex-col gap-1">
      <span className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="truncate">{name ?? t("ch.catalog.none")}</span>
        {channel.catalog_state === "unchecked" ? (
          <span className="text-xs text-muted-foreground">{t("ch.catalog.unchecked")}</span>
        ) : null}
        {/* Coexistencia: el catálogo vive en la app del teléfono; la consola
            apunta cuál es y no finge haberlo comprobado con Meta. */}
        {channel.catalog_state === "coexistence" ? (
          <span className="text-xs text-muted-foreground">{t("ch.catalog.coexistence")}</span>
        ) : null}
        {manage && name === null ? (
          <Button type="button" size="sm" variant="outline" onClick={onConnect} disabled={pending}>
            {t("ch.catalog.connect")}
          </Button>
        ) : null}
        {manage && name !== null ? (
          <>
            <Button type="button" size="sm" variant="outline" onClick={onConnect} disabled={pending}>
              {t("ch.catalog.change")}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={onClear} disabled={pending}>
              {t("ch.catalog.clear")}
            </Button>
          </>
        ) : null}
      </span>
      {channel.catalog_error ? (
        <span className="text-xs text-destructive">
          {errorKey ? t(errorKey, { message: channel.catalog_error.message ?? "" }) : t("common.error.backend")}
        </span>
      ) : null}
    </span>
  );
}
