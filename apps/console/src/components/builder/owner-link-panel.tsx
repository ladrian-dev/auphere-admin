"use client";

import { Copy, Mail, MessageCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, ConfirmDialog, Input, formatDateTime } from "@nexus/ui";

import { createOwnerLinkAction, revokeOwnerLinkAction } from "@/app/(console)/clients/[ref]/agents/channel-actions";
import { BrandLogo } from "@/components/brand-logo";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { OwnerLink, OwnerLinkMode, PendingOwnerLink } from "@/lib/backend/channel-config-types";

import type { Result } from "./builder-model";
import { OWNER_LINK_MODES, ownerLinkCopy, ownerLinkModeName } from "./channel-model";

type Ids = { ref: string; agent: string };
export type OwnerLinkActions = {
  create: (body: Ids & { mode: OwnerLinkMode; replace?: boolean }) => Promise<Result<OwnerLink>>;
  revoke: (body: Ids & { link: string }) => Promise<Result<null>>;
};

export const OWNER_LINK_ACTIONS: OwnerLinkActions = {
  create: (body) => createOwnerLinkAction(body),
  revoke: (body) => revokeOwnerLinkAction(body),
};

/**
 * El enlace del dueño, por agente (spec 047, requisito 31; T111): el dueño del
 * negocio conecta el número él mismo, con su cuenta de Meta, y el número queda
 * en este agente.
 *
 * - El enlace solo se ve al crearlo: se ofrece copiarlo mientras sigue en
 *   pantalla, porque la API guarda su huella y no puede volver a enseñarlo (31.1, 31.7).
 * - Como mucho uno pendiente por agente: crear otro ofrece «Revocar y crear» (31.2).
 * - El pendiente dice su modo y su caducidad, y se puede revocar (31.7).
 * - «WhatsApp login» solo si la API lo acepta para el país del negocio; si no,
 *   se dice y la opción desaparece. Nunca se promete «sin Facebook» (31.6).
 * - «desde su teléfono» solo con la bandera, hasta probarlo en iOS y Android (31.3).
 *
 * Quien solo lee ve el pendiente, sin botones (§V).
 *
 * Como el prototipo aprobado (`agente.md` §7.3 y §10.1, hueco H4): el
 * pendiente es la tarjeta «Enlace enviado al cliente · WhatsApp» de la pestaña
 * Canales, y crear uno es el paso «Compartir un enlace» del modal «Conectar
 * WhatsApp» (`bare`: sin marco ni título, los pone el modal). `onCreated`,
 * `onDone` y `onRevoked` avisan a la pestaña para que pinte o quite la tarjeta.
 */
export function OwnerLinkPanel({
  refId,
  agentId,
  pending: initial,
  canWrite,
  fromPhone = false,
  actions = OWNER_LINK_ACTIONS,
  bare = false,
  initialMode = "coexistence",
  onCreated,
  onDone,
  onRevoked,
}: {
  refId: string;
  agentId: string;
  pending: PendingOwnerLink | null;
  canWrite: boolean;
  fromPhone?: boolean;
  actions?: OwnerLinkActions;
  /** Dentro del modal «Conectar WhatsApp»: sin marco, sin título y sin la explicación (la dice el modal). */
  bare?: boolean;
  /** El modo que se eligió en el modal. */
  initialMode?: OwnerLinkMode;
  onCreated?: (pending: PendingOwnerLink) => void;
  /** «Hecho» (o «Listo, ya lo compartí» dentro del modal). */
  onDone?: () => void;
  onRevoked?: () => void;
}) {
  const t = useT();
  const locale = useLocale();
  const base = React.useId();
  const copy = ownerLinkCopy(fromPhone);
  const ids = { ref: refId, agent: agentId };
  const [pending, setPending] = React.useState(initial);
  const [creating, setCreating] = React.useState(!initial);
  const [mode, setMode] = React.useState<OwnerLinkMode>(initialMode);
  const [loginUnavailable, setLoginUnavailable] = React.useState(false);
  const [exists, setExists] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [created, setCreated] = React.useState<OwnerLink | null>(null);
  const [confirmRevoke, setConfirmRevoke] = React.useState(false);

  if (!canWrite && !pending) return null;
  const modes = OWNER_LINK_MODES.filter((m) => !(m === "whatsapp_login" && loginUnavailable));

  async function create(replace: boolean) {
    setBusy(true);
    setError(null);
    const res = await actions.create({ ...ids, mode, ...(replace ? { replace: true } : {}) });
    setBusy(false);
    if (res.ok) {
      const next = { id: res.data.id, mode: res.data.mode, expires_at: res.data.expires_at };
      setCreated(res.data);
      setExists(false);
      setPending(next);
      onCreated?.(next);
      return;
    }
    if (res.code === "link_pending_exists") {
      setExists(true);
      return;
    }
    if (res.code === "whatsapp_login_unavailable") {
      setLoginUnavailable(true);
      setMode("coexistence");
      setError(t("builder.ownerLink.unavailable"));
      return;
    }
    setError(res.status === 401 || res.status === 403 ? t("common.forbidden") : t("builder.channel.error"));
  }

  async function revoke() {
    if (!pending) return;
    const res = await actions.revoke({ ...ids, link: pending.id });
    if (!res.ok) {
      toast.error(t("builder.channel.error"));
      return;
    }
    setConfirmRevoke(false);
    setPending(null);
    setCreating(true);
    toast.success(t("builder.ownerLink.revoked"));
    onRevoked?.();
  }

  async function copyLink() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.url);
      toast.success(t("builder.ownerLink.copied"));
    } catch {
      toast.error(t("builder.channel.error"));
    }
  }

  const message = created ? t(copy.message, { url: created.url }) : "";

  const showsPending = Boolean(pending && !creating && !created);
  const body = (
    <>
      {created ? (
        <div className="grid min-w-0 gap-3" data-slot="owner-link-created">
          <Callout tone="positive">{t("builder.ownerLink.ready")}</Callout>
          <div className="flex min-w-0 flex-wrap gap-2">
            <Input
              readOnly
              value={created.url}
              aria-label={t("builder.ownerLink.url")}
              className="min-w-0 flex-1 basis-56 font-mono text-xs"
              onFocus={(e) => e.currentTarget.select()}
            />
            <Button onClick={() => void copyLink()}>
              <Copy aria-hidden="true" />
              {t("builder.ownerLink.copy")}
            </Button>
          </div>
          <div className="flex min-w-0 flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              nativeButton={false}
              render={<a href={`https://wa.me/?text=${encodeURIComponent(message)}`} target="_blank" rel="noreferrer" />}
            >
              <MessageCircle aria-hidden="true" />
              {t("builder.ownerLink.whatsapp")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              nativeButton={false}
              render={<a href={`mailto:?subject=${encodeURIComponent(t("builder.ownerLink.subject"))}&body=${encodeURIComponent(message)}`} />}
            >
              <Mail aria-hidden="true" />
              {t("builder.ownerLink.email")}
            </Button>
            <Button
              variant={bare ? "default" : "ghost"}
              size="sm"
              onClick={() => {
                setCreated(null);
                setCreating(false);
                onDone?.();
              }}
            >
              {bare ? t("channels.proto.link.done") : t("builder.ownerLink.done")}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">{t("builder.ownerLink.expires", { date: formatDateTime(created.expires_at, locale) })}</p>
        </div>
      ) : pending && !creating ? (
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-3" data-slot="owner-link-pending">
          <div className="grid min-w-0 flex-1 basis-64 gap-1 text-sm">
            <span className="text-muted-foreground">{t("builder.ownerLink.pending", { mode: ownerLinkModeName(t, pending.mode) })}</span>
            <span className="text-xs text-pretty text-muted-foreground">
              {t("channels.proto.linkCard.note", { date: formatDateTime(pending.expires_at, locale) })}
            </span>
          </div>
          {canWrite ? (
            <span className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => setCreating(true)}>
                {t("builder.ownerLink.another")}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirmRevoke(true)}>
                {t("builder.ownerLink.revoke")}
              </Button>
            </span>
          ) : null}
        </div>
      ) : canWrite ? (
        <form
          className="grid min-w-0 gap-3"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void create(Boolean(pending) || exists);
          }}
          data-slot="owner-link-form"
        >
          {bare ? null : <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t(copy.body)}</p>}
          <fieldset className="grid min-w-0 gap-2">
            <legend className="mb-1 text-sm font-medium">{t("builder.ownerLink.mode")}</legend>
            {modes.map((m) => (
              <label key={m} className="flex min-h-6 min-w-0 items-start gap-2 text-sm">
                <input
                  type="radio"
                  name={`${base}-mode`}
                  value={m}
                  className="mt-1 size-4 shrink-0 accent-primary"
                  checked={mode === m}
                  onChange={() => {
                    setMode(m);
                    setError(null);
                  }}
                />
                <span className="grid min-w-0 gap-1">
                  <span className="text-pretty">{t(`builder.ownerLink.mode.${m}` as MessageKey)}</span>
                  <span className="text-xs text-pretty text-muted-foreground">{t(`builder.ownerLink.mode.${m}.hint` as MessageKey)}</span>
                </span>
              </label>
            ))}
          </fieldset>
          {pending || exists ? <Callout tone="warning">{t("builder.ownerLink.replaces")}</Callout> : null}
          {error ? (
            <p role="alert" className="text-sm text-pretty text-destructive">
              {error}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="sm" loading={busy}>
              {pending || exists ? t("builder.ownerLink.replace") : t("builder.ownerLink.create")}
            </Button>
            {pending ? (
              <Button type="button" size="sm" variant="ghost" onClick={() => setCreating(false)} disabled={busy}>
                {t("builder.channel.cancel")}
              </Button>
            ) : null}
          </div>
        </form>
      ) : null}

      <ConfirmDialog
        open={confirmRevoke}
        onOpenChange={setConfirmRevoke}
        title={t("builder.ownerLink.revoke.title")}
        description={t("builder.ownerLink.revoke.body")}
        confirmLabel={t("builder.ownerLink.revoke")}
        cancelLabel={t("builder.channel.cancel")}
        destructive
        onConfirm={revoke}
      />
    </>
  );

  if (bare) {
    return (
      <div className="grid min-w-0 gap-3" data-slot="owner-link">
        {body}
      </div>
    );
  }
  return (
    <section aria-labelledby={`${base}-title`} className="flex min-w-0 items-start gap-3 rounded-lg border border-border bg-card p-4" data-slot="owner-link">
      <BrandLogo brand="whatsapp" size="md" />
      <div className="grid min-w-0 flex-1 gap-3">
        <p id={`${base}-title`} className="font-medium text-pretty">
          {showsPending ? t("channels.proto.linkCard.title") : t("builder.ownerLink.title")}
        </p>
        {body}
      </div>
    </section>
  );
}
